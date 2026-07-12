"""Unit tests for plugin dependency resolution.

Tests DependencyGraph (topological sort, cycle detection, depth),
DependencyResolver (resolve, missing, circular, depth, version conflicts),
and version comparison helpers.
"""

import pytest

from tokenade.core.integration.dependency_graph import (
    DependencyGraph,
    MAX_DEPTH,
)
from tokenade.core.integration.dependency_resolver import (
    DependencyResolver,
    _compare_versions,
    _parse_version,
    is_major_version_mismatch,
)


class TestVersionHelpers:
    """Tests for version comparison helpers."""

    def test_parse_version(self):
        assert _parse_version("1.0.0") == (1, 0, 0)
        assert _parse_version("2.3.5") == (2, 3, 5)
        assert _parse_version("v1.2.3") == (1, 2, 3)
        assert _parse_version("1.0") == (1, 0, 0)
        assert _parse_version("1") == (1, 0, 0)
        assert _parse_version("invalid") == (0, 0, 0)
        assert _parse_version("") == (0, 0, 0)

    def test_compare_versions(self):
        assert _compare_versions("1.0.0", "1.0.0") == 0
        assert _compare_versions("2.0.0", "1.0.0") == 1
        assert _compare_versions("1.0.0", "2.0.0") == -1
        assert _compare_versions("1.1.0", "1.0.0") == 1
        assert _compare_versions("1.0.1", "1.0.0") == 1
        assert _compare_versions("1.0.0", "1.0.1") == -1
        assert _compare_versions("2.10.0", "2.9.0") == 1

    def test_is_major_version_mismatch(self):
        assert is_major_version_mismatch("1.0.0", "2.0.0") is True
        assert is_major_version_mismatch("1.0.0", "1.5.0") is False
        assert is_major_version_mismatch("3.0.0", "3.2.1") is False
        assert is_major_version_mismatch("1.0.0", "1.0.0") is False


class TestDependencyGraph:
    """Tests for DependencyGraph."""

    def test_add_and_get_dependencies(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b", "c"])
        graph.add_plugin("b", [])
        graph.add_plugin("c", [])

        assert graph.get_dependencies("a") == ["b", "c"]
        assert graph.get_dependencies("b") == []
        assert graph.get_all_plugins() == ["a", "b", "c"]

    def test_remove_plugin(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        graph.remove_plugin("a")
        assert "a" not in graph.get_all_plugins()
        assert "b" in graph.get_all_plugins()
        # b should no longer have a as a dependent
        assert "a" not in graph.get_dependents("b")

    def test_get_dependents(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("c", ["b"])
        graph.add_plugin("b", [])

        dependents = graph.get_dependents("b")
        assert "a" in dependents
        assert "c" in dependents

    def test_topological_sort_simple(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        order = graph.topological_sort()
        assert order.index("b") < order.index("a")

    def test_topological_sort_chain(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", ["c"])
        graph.add_plugin("c", ["d"])
        graph.add_plugin("d", [])

        order = graph.topological_sort()
        assert order.index("d") < order.index("c")
        assert order.index("c") < order.index("b")
        assert order.index("b") < order.index("a")

    def test_topological_sort_diamond(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b", "c"])
        graph.add_plugin("b", ["d"])
        graph.add_plugin("c", ["d"])
        graph.add_plugin("d", [])

        order = graph.topological_sort()
        assert order.index("d") < order.index("b")
        assert order.index("d") < order.index("c")
        assert order.index("b") < order.index("a")
        assert order.index("c") < order.index("a")

    def test_cycle_detection_no_cycle(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        assert graph.has_cycle() is False

    def test_cycle_detection_simple(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", ["a"])

        assert graph.has_cycle() is True

    def test_cycle_detection_complex(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", ["c"])
        graph.add_plugin("c", ["a"])

        assert graph.has_cycle() is True

    def test_cycle_detection_self_loop(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["a"])

        assert graph.has_cycle() is True

    def test_depth_no_deps(self):
        graph = DependencyGraph()
        graph.add_plugin("a", [])

        assert graph.get_depth("a") == 0

    def test_depth_one_level(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        assert graph.get_depth("a") == 1
        assert graph.get_depth("b") == 0

    def test_depth_chain(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", ["c"])
        graph.add_plugin("c", ["d"])
        graph.add_plugin("d", [])

        assert graph.get_depth("a") == 3
        assert graph.get_depth("d") == 0

    def test_depth_not_found(self):
        graph = DependencyGraph()
        assert graph.get_depth("nonexistent") == -1

    def test_validate_no_errors(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        assert graph.validate() == []

    def test_validate_cycle(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", ["a"])

        errors = graph.validate()
        assert len(errors) > 0
        assert any("Circular" in e for e in errors)

    def test_validate_missing_dep(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        # b not added to graph

        errors = graph.validate()
        assert len(errors) > 0
        assert any("not in the graph" in e for e in errors)

    def test_validate_depth_exceeded(self):
        graph = DependencyGraph()
        # Create a chain of length > MAX_DEPTH
        for i in range(MAX_DEPTH + 2):
            deps = [f"dep-{i - 1}"] if i > 0 else []
            graph.add_plugin(f"dep-{i}", deps)

        errors = graph.validate()
        assert len(errors) > 0
        assert any("depth" in e for e in errors)

    def test_get_load_order(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b", "c"])
        graph.add_plugin("b", ["d"])
        graph.add_plugin("c", ["d"])
        graph.add_plugin("d", [])

        # Load order for "a" should include all deps
        order = graph.get_load_order("a")
        assert "d" in order
        assert "b" in order
        assert "c" in order
        assert "a" in order
        # d should come before b and c
        assert order.index("d") < order.index("b")
        assert order.index("d") < order.index("c")
        # b and c should come before a
        assert order.index("b") < order.index("a")
        assert order.index("c") < order.index("a")

    def test_get_load_order_not_found(self):
        graph = DependencyGraph()
        with pytest.raises(ValueError, match="not in graph"):
            graph.get_load_order("nonexistent")


class TestDependencyResolver:
    """Tests for DependencyResolver."""

    def test_resolve(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        resolver = DependencyResolver(graph)
        order = resolver.resolve("a")
        assert order.index("b") < order.index("a")

    def test_resolve_all(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])
        graph.add_plugin("c", [])

        resolver = DependencyResolver(graph)
        order = resolver.resolve_all()
        assert "b" in order
        assert "a" in order
        assert "c" in order
        assert order.index("b") < order.index("a")

    def test_check_missing_no_missing(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        resolver = DependencyResolver(graph)
        assert resolver.check_missing() == []

    def test_check_missing_dependency(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        # b not in graph, no registry

        resolver = DependencyResolver(graph)
        missing = resolver.check_missing()
        assert "b" in missing

    def test_check_circular_no_cycle(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        resolver = DependencyResolver(graph)
        assert resolver.check_circular() == []

    def test_check_circular_detected(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", ["a"])

        resolver = DependencyResolver(graph)
        circular = resolver.check_circular()
        assert len(circular) > 0
        assert "a" in circular or "b" in circular

    def test_check_depth_ok(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        resolver = DependencyResolver(graph)
        assert resolver.check_depth() == []

    def test_check_depth_exceeded(self):
        graph = DependencyGraph()
        for i in range(MAX_DEPTH + 2):
            deps = [f"dep-{i - 1}"] if i > 0 else []
            graph.add_plugin(f"dep-{i}", deps)

        resolver = DependencyResolver(graph)
        errors = resolver.check_depth()
        assert len(errors) > 0

    def test_version_conflict_latest_wins(self):
        graph = DependencyGraph()
        graph.add_plugin("a", [])
        graph.add_plugin("b", [])

        resolver = DependencyResolver(graph, registry_manager=None)
        # Without registry, required version is used
        resolved = resolver.resolve_version_conflicts({
            "dep1": "1.0.0",
            "dep2": "2.1.0",
        })
        assert resolved["dep1"] == "1.0.0"
        assert resolved["dep2"] == "2.1.0"

    def test_get_dependency_tree(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b", "c"])
        graph.add_plugin("b", [])
        graph.add_plugin("c", [])

        resolver = DependencyResolver(graph)
        tree = resolver.get_dependency_tree("a")
        assert "a" in tree
        assert "b" in tree
        assert "c" in tree

    def test_get_dependency_tree_with_missing(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        # b not in graph

        resolver = DependencyResolver(graph)
        tree = resolver.get_dependency_tree("a")
        assert "a" in tree
        assert "b" in tree
        assert "missing" in tree

    def test_install_with_dependencies_no_registry(self):
        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        resolver = DependencyResolver(graph, registry_manager=None)
        result = resolver.install_with_dependencies("a")
        # Without registry, should fail
        assert result is False

    def test_install_with_dependencies_with_mock_registry(self):
        """Test install with a mock registry."""
        from unittest.mock import MagicMock

        graph = DependencyGraph()
        graph.add_plugin("a", ["b"])
        graph.add_plugin("b", [])

        mock_registry = MagicMock()
        mock_registry.install.return_value = True

        resolver = DependencyResolver(graph, registry_manager=mock_registry)
        # Plugins are already in graph, so no install needed
        result = resolver.install_with_dependencies("a")
        # Should return True since all deps are already in graph
        assert result is True


class TestMaxDepth:
    """Tests for depth limit enforcement."""

    def test_max_depth_value(self):
        assert MAX_DEPTH == 5

    def test_depth_at_limit_ok(self):
        graph = DependencyGraph()
        for i in range(5):
            deps = [f"dep-{i - 1}"] if i > 0 else []
            graph.add_plugin(f"dep-{i}", deps)

        # dep-4 has depth 4 (within limit)
        errors = graph.validate()
        depth_errors = [e for e in errors if "depth" in e.lower()]
        assert depth_errors == []

    def test_depth_over_limit(self):
        graph = DependencyGraph()
        for i in range(7):
            deps = [f"dep-{i - 1}"] if i > 0 else []
            graph.add_plugin(f"dep-{i}", deps)

        errors = graph.validate()
        depth_errors = [e for e in errors if "depth" in e.lower()]
        assert len(depth_errors) > 0
