"""Dependency resolver for plugin loading.

Uses DependencyGraph to determine load order, check for missing
dependencies, detect circular dependencies, enforce depth limits,
and resolve version conflicts (latest version wins).

Version comparison uses semver (major.minor.patch). Major version
mismatch is a conflict that rejects the plugin.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from tokenade.core.integration.dependency_graph import (
    DependencyGraph,
    MAX_DEPTH,
)

logger = logging.getLogger(__name__)


def _parse_version(version: str) -> Tuple[int, int, int]:
    """Parse a semver string into (major, minor, patch).

    Returns (0, 0, 0) if parsing fails.
    """
    try:
        # Strip leading 'v' if present
        version = version.lstrip("v")
        parts = version.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        return (0, 0, 0)


def _compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings.

    Returns:
        1 if v1 > v2
        0 if v1 == v2
        -1 if v1 < v2
    """
    major1, minor1, patch1 = _parse_version(v1)
    major2, minor2, patch2 = _parse_version(v2)

    if major1 != major2:
        return 1 if major1 > major2 else -1
    if minor1 != minor2:
        return 1 if minor1 > minor2 else -1
    if patch1 != patch2:
        return 1 if patch1 > patch2 else -1
    return 0


def is_major_version_mismatch(v1: str, v2: str) -> bool:
    """Check if two versions have different major versions.

    Args:
        v1: First version string
        v2: Second version string

    Returns:
        True if major versions differ
    """
    major1 = _parse_version(v1)[0]
    major2 = _parse_version(v2)[0]
    return major1 != major2


class DependencyResolver:
    """Resolves plugin dependencies for loading and installation.

    Uses a DependencyGraph to determine load order, check for missing
    dependencies, enforce depth limits, and resolve version conflicts.

    Example:
        graph = DependencyGraph()
        resolver = DependencyResolver(graph)
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])
        load_order = resolver.resolve("a")  # ["b", "a"]
    """

    def __init__(
        self,
        graph: DependencyGraph,
        registry_manager: Any = None,
    ) -> None:
        """Initialize the resolver.

        Args:
            graph: The dependency graph to use
            registry_manager: Optional PluginRegistry for installing
                              missing dependencies
        """
        self._graph = graph
        self._registry = registry_manager

    def resolve(self, plugin_name: str) -> List[str]:
        """Resolve dependencies for a plugin and return load order.

        Args:
            plugin_name: The plugin to resolve

        Returns:
            List of plugin names in dependency order (dependencies first)

        Raises:
            ValueError: If plugin not found or circular dependency detected
        """
        if plugin_name not in self._graph.get_all_plugins() and self._registry:
            # Try to install the plugin itself
            self._install_dependency(plugin_name)
            # After install, the graph should have it
            # But we won't have added it to the graph here —
            # that's done by the caller who manages the graph

        return self._graph.get_load_order(plugin_name)

    def resolve_all(self) -> List[str]:
        """Resolve all plugins in the graph and return load order.

        Returns:
            List of all plugin names in dependency order

        Raises:
            ValueError: If circular dependency detected
        """
        return self._graph.topological_sort()

    def check_missing(self) -> List[str]:
        """Check for missing dependencies.

        A dependency is "missing" if it's not in the graph and
        not available in the registry.

        Returns:
            List of missing dependency names
        """
        missing = []
        for name in self._graph.get_all_plugins():
            for dep in self._graph.get_dependencies(name):
                if dep not in self._graph.get_all_plugins():
                    # Check if available in registry
                    if self._registry is None:
                        missing.append(dep)
                    else:
                        try:
                            info = self._registry.search(dep)
                            if not info:
                                missing.append(dep)
                        except Exception:
                            missing.append(dep)
        return list(set(missing))  # deduplicate

    def check_circular(self) -> List[str]:
        """Check for circular dependencies.

        Returns:
            List of plugin names involved in circular dependencies
            (empty if no cycles)
        """
        if not self._graph.has_cycle():
            return []

        # Find the nodes involved in cycles by attempting topo sort
        try:
            self._graph.topological_sort()
            return []
        except ValueError as e:
            # Extract node names from the error message
            msg = str(e)
            # Parse the error to find plugin names
            # The error is: "Circular dependency detected involving: ['a', 'b']"
            # Extract the list portion
            import ast
            try:
                list_str = msg.split("involving: ")[1]
                nodes = ast.literal_eval(list_str)
                return nodes
            except (IndexError, ValueError):
                return []

    def check_depth(self) -> List[str]:
        """Check for plugins that exceed the depth limit.

        Returns:
            List of error messages for plugins exceeding depth limit
        """
        errors = []
        for name in self._graph.get_all_plugins():
            depth = self._graph.get_depth(name)
            if depth > MAX_DEPTH:
                errors.append(
                    f"Plugin {name} has depth {depth} (max {MAX_DEPTH})"
                )
        return errors

    def resolve_version_conflicts(
        self,
        required_versions: Dict[str, str],
    ) -> Dict[str, str]:
        """Resolve version conflicts (latest version wins).

        Args:
            required_versions: Dict mapping dependency name to required version

        Returns:
            Dict mapping dependency name to resolved version
        """
        resolved = {}
        for dep_name, required_version in required_versions.items():
            # If we have a registry, search for the latest version
            if self._registry is not None:
                try:
                    results = self._registry.search(dep_name)
                    if results:
                        # Find the latest version
                        latest = max(
                            results,
                            key=lambda r: _parse_version(
                                r.get("version", "0.0.0")
                            ),
                        )
                        latest_version = latest.get("version", "0.0.0")

                        # Check major version compatibility
                        if is_major_version_mismatch(
                            required_version, latest_version
                        ):
                            logger.warning(
                                f"Major version conflict for {dep_name}: "
                                f"required {required_version}, "
                                f"latest {latest_version}"
                            )
                            # Use required version — major mismatch is a conflict
                            resolved[dep_name] = required_version
                        else:
                            # Latest version wins
                            if _compare_versions(
                                latest_version, required_version
                            ) > 0:
                                logger.info(
                                    f"Using latest version {latest_version} "
                                    f"for {dep_name} (required {required_version})"
                                )
                            resolved[dep_name] = latest_version
                    else:
                        resolved[dep_name] = required_version
                except Exception as e:
                    logger.debug(
                        f"Failed to search registry for {dep_name}: {e}"
                    )
                    resolved[dep_name] = required_version
            else:
                resolved[dep_name] = required_version

        return resolved

    def install_with_dependencies(self, plugin_name: str) -> bool:
        """Install a plugin and all its missing dependencies.

        Args:
            plugin_name: The plugin to install

        Returns:
            True if installation succeeded, False otherwise
        """
        if self._registry is None:
            logger.error("No registry manager available for installation")
            return False

        # Get load order (includes all transitive dependencies)
        try:
            load_order = self._graph.get_load_order(plugin_name)
        except ValueError as e:
            logger.error(f"Cannot resolve {plugin_name}: {e}")
            return False

        # Install each dependency in order
        for dep_name in load_order:
            if dep_name not in self._graph.get_all_plugins():
                if not self._install_dependency(dep_name):
                    logger.error(f"Failed to install dependency: {dep_name}")
                    return False

        # Install the plugin itself
        if plugin_name not in self._graph.get_all_plugins():
            if not self._install_dependency(plugin_name):
                return False

        return True

    def _install_dependency(self, dep_name: str) -> bool:
        """Install a single dependency from the registry.

        Args:
            dep_name: Dependency name to install

        Returns:
            True if installed successfully, False otherwise
        """
        if self._registry is None:
            return False

        try:
            result = self._registry.install(dep_name)
            if result:
                logger.info(f"Installed dependency: {dep_name}")
                return True
            else:
                logger.warning(f"Failed to install dependency: {dep_name}")
                return False
        except Exception as e:
            logger.error(f"Error installing {dep_name}: {e}")
            return False

    def get_dependency_tree(
        self, plugin_name: str, indent: int = 0
    ) -> str:
        """Get a formatted dependency tree for a plugin.

        Args:
            plugin_name: The plugin to show dependencies for
            indent: Current indentation level (for recursive calls)

        Returns:
            Formatted tree string
        """
        prefix = "  " * indent
        result = f"{prefix}{plugin_name}\n"

        deps = self._graph.get_dependencies(plugin_name)
        for dep in deps:
            if dep in self._graph.get_all_plugins():
                result += self.get_dependency_tree(dep, indent + 1)
            else:
                result += f"{'  ' * (indent + 1)}{dep} (missing)\n"

        return result
