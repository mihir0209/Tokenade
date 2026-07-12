"""Dependency graph for plugin resolution.

Builds a directed graph from plugin manifests, performs topological sort
for load ordering, detects circular dependencies, and calculates depth.

Used by DependencyResolver to determine:
- Load order (topological sort)
- Circular dependencies (DFS cycle detection)
- Depth limit enforcement (max 5)
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

MAX_DEPTH = 5


class DependencyGraph:
    """Directed graph of plugin dependencies.

    Plugins are nodes; edges point from a plugin to its dependencies.
    Topological sort returns plugins in dependency order (dependencies first).

    Example:
        graph = DependencyGraph()
        graph.add_plugin("a", dependencies=["b", "c"])
        graph.add_plugin("b", dependencies=[])
        graph.add_plugin("c", dependencies=["b"])
        load_order = graph.topological_sort()  # ["b", "c", "a"]
    """

    def __init__(self):
        # name → list of dependency names
        self._deps: Dict[str, List[str]] = {}
        # name → list of plugins that depend on it (reverse edges)
        self._dependents: Dict[str, List[str]] = defaultdict(list)

    def add_plugin(self, name: str, dependencies: List[str]) -> None:
        """Add a plugin and its dependencies to the graph.

        Args:
            name: Plugin name
            dependencies: List of plugin names this plugin depends on
        """
        self._deps[name] = list(dependencies)
        for dep in dependencies:
            if dep not in self._dependents:
                self._dependents[dep] = []
            self._dependents[dep].append(name)
        logger.debug(
            f"Added plugin {name} with dependencies: {dependencies}"
        )

    def remove_plugin(self, name: str) -> None:
        """Remove a plugin from the graph.

        Args:
            name: Plugin name to remove
        """
        deps = self._deps.pop(name, [])
        for dep in deps:
            if dep in self._dependents:
                self._dependents[dep] = [
                    d for d in self._dependents[dep] if d != name
                ]
        # Also remove from reverse edges
        if name in self._dependents:
            del self._dependents[name]

    def get_dependencies(self, name: str) -> List[str]:
        """Get direct dependencies of a plugin.

        Args:
            name: Plugin name

        Returns:
            List of dependency names (empty if not found)
        """
        return list(self._deps.get(name, []))

    def get_dependents(self, name: str) -> List[str]:
        """Get plugins that directly depend on this plugin.

        Args:
            name: Plugin name

        Returns:
            List of plugin names that depend on this plugin
        """
        return list(self._dependents.get(name, []))

    def get_all_plugins(self) -> List[str]:
        """Get all plugin names in the graph.

        Returns:
            List of all plugin names
        """
        return list(self._deps.keys())

    def topological_sort(self) -> List[str]:
        """Return plugins in dependency order (dependencies first).

        Uses Kahn's algorithm (BFS-based topological sort).

        Returns:
            List of plugin names in load order

        Raises:
            ValueError: If a circular dependency is detected
        """
        # Build in-degree map
        in_degree: Dict[str, int] = {name: 0 for name in self._deps}
        for name, deps in self._deps.items():
            for dep in deps:
                if dep in in_degree:
                    pass  # dep is a known plugin
            # in_degree = number of dependencies that are in the graph
            in_degree[name] = sum(1 for d in deps if d in in_degree)

        # Start with plugins that have no dependencies
        queue = [name for name, degree in in_degree.items() if degree == 0]
        queue.sort()  # deterministic order
        result = []

        while queue:
            name = queue.pop(0)
            result.append(name)
            # For each plugin that depends on this one, decrement in-degree
            for dependent in sorted(self._dependents.get(name, [])):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
            queue.sort()  # keep deterministic

        if len(result) != len(self._deps):
            # Circular dependency detected
            remaining = [n for n in self._deps if n not in result]
            raise ValueError(
                f"Circular dependency detected involving: {remaining}"
            )

        return result

    def has_cycle(self) -> bool:
        """Check if the graph contains a circular dependency.

        Uses DFS with three-color marking.

        Returns:
            True if a cycle exists, False otherwise
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {name: WHITE for name in self._deps}

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for dep in self._deps.get(node, []):
                if dep not in color:
                    continue  # external dependency
                if color[dep] == GRAY:
                    return True  # back edge → cycle
                if color[dep] == WHITE and dfs(dep):
                    return True
            color[node] = BLACK
            return False

        for name in self._deps:
            if color[name] == WHITE:
                if dfs(name):
                    return True
        return False

    def get_depth(self, name: str) -> int:
        """Get the dependency depth of a plugin.

        Depth 0 = no dependencies
        Depth N = deepest dependency chain is N levels

        Args:
            name: Plugin name

        Returns:
            Depth (0-based), or -1 if plugin not found
        """
        if name not in self._deps:
            return -1

        def calc_depth(node: str, visited: Set[str]) -> int:
            if node in visited:
                # Cycle — return 0 for this path
                return 0
            visited.add(node)
            deps = self._deps.get(node, [])
            if not deps:
                visited.discard(node)
                return 0
            max_child_depth = 0
            for dep in deps:
                if dep in self._deps:
                    child_depth = calc_depth(dep, visited)
                    max_child_depth = max(max_child_depth, child_depth)
            visited.discard(node)
            return max_child_depth + 1

        return calc_depth(name, set())

    def validate(self) -> List[str]:
        """Validate the graph and return a list of errors.

        Checks:
        - Circular dependencies
        - Depth limit (MAX_DEPTH = 5)
        - Missing dependencies (deps not in graph)

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check for cycles
        if self.has_cycle():
            # Find the nodes involved in cycles
            try:
                self.topological_sort()
            except ValueError as e:
                errors.append(str(e))

        # Check depth limit
        for name in self._deps:
            depth = self.get_depth(name)
            if depth > MAX_DEPTH:
                errors.append(
                    f"Plugin {name} has dependency depth {depth} "
                    f"(max {MAX_DEPTH})"
                )

        # Check for missing dependencies (deps not in graph)
        for name, deps in self._deps.items():
            for dep in deps:
                if dep not in self._deps:
                    errors.append(
                        f"Plugin {name} depends on '{dep}' "
                        f"which is not in the graph"
                    )

        return errors

    def get_load_order(self, plugin_name: str) -> List[str]:
        """Get the load order for a specific plugin and its dependencies.

        Args:
            plugin_name: The plugin to load

        Returns:
            List of plugin names in dependency order (dependencies first,
            plugin_name last)

        Raises:
            ValueError: If plugin not found or circular dependency detected
        """
        if plugin_name not in self._deps:
            raise ValueError(f"Plugin '{plugin_name}' not in graph")

        # Collect all transitive dependencies
        visited: Set[str] = set()
        order: List[str] = []

        def visit(node: str) -> None:
            if node in visited:
                return
            visited.add(node)
            for dep in self._deps.get(node, []):
                if dep in self._deps:
                    visit(dep)
            order.append(node)

        visit(plugin_name)
        return order

    def __repr__(self) -> str:
        return f"DependencyGraph(plugins={len(self._deps)})"
