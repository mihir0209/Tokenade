"""Tests for Phase 38: Plugin Marketplace."""
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def tmp_plugins_dir():
    """Create a temporary plugins directory."""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_plugins():
    """Sample plugin metadata for testing."""
    return [
        {
            "name": "tokenade-oauth2",
            "version": "1.0.0",
            "description": "OAuth2 token refresh plugin",
            "author": "tokenade",
            "url": "https://github.com/mihir0209/tokenade",
            "type": "session_refresh",
            "entry_point": "plugin.py",
            "category": "authentication",
            "tags": ["oauth2", "google", "token"],
            "rating": 4.5,
            "review_count": 10,
            "downloads": 1000,
            "verified": True,
        },
        {
            "name": "tokenade-export-json",
            "version": "1.0.0",
            "description": "JSON export format plugin",
            "author": "tokenade",
            "url": "https://github.com/mihir0209/tokenade",
            "type": "export_format",
            "entry_point": "plugin.py",
            "category": "export-formats",
            "tags": ["json", "export"],
            "rating": 4.0,
            "review_count": 5,
            "downloads": 500,
            "verified": True,
        },
        {
            "name": "tokenade-notify-slack",
            "version": "1.0.0",
            "description": "Slack webhook notifications",
            "author": "community",
            "url": "https://github.com/mihir0209/tokenade",
            "type": "handler",
            "entry_point": "plugin.py",
            "category": "notifications",
            "tags": ["slack", "webhook", "notify"],
            "rating": 3.5,
            "review_count": 3,
            "downloads": 200,
            "verified": False,
        },
    ]


# ─── PluginRegistry Tests ──────────────────────────────────────

class TestPluginRegistrySearch:
    """Test PluginRegistry search, categories, ratings."""

    def test_search_returns_all_when_no_filters(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search()
        assert len(results) == 3

    def test_search_by_query_name(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search(query="oauth2")
        assert len(results) >= 1
        assert any("oauth2" in p["name"].lower() for p in results)

    def test_search_by_query_description(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search(query="slack")
        assert len(results) >= 1
        assert any("slack" in p["description"].lower() for p in results)

    def test_search_by_query_tag(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search(query="webhook")
        assert len(results) >= 1

    def test_search_by_type(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search(plugin_type="session_refresh")
        assert len(results) == 1
        assert results[0]["name"] == "tokenade-oauth2"

    def test_search_by_category(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search(category="authentication")
        assert len(results) == 1
        assert results[0]["category"] == "authentication"

    def test_search_by_tags(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search(tags=["google"])
        assert len(results) >= 1

    def test_search_sort_by_downloads(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search(sort_by="downloads")
        assert results[0]["downloads"] >= results[1]["downloads"]

    def test_search_sort_by_name(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search(sort_by="name")
        names = [p["name"] for p in results]
        assert names == sorted(names)

    def test_search_no_results(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            results = registry.search(query="nonexistent_plugin_xyz")
        assert len(results) == 0

    def test_get_categories(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            categories = registry.get_categories()
        assert len(categories) >= 5
        cat_names = [c["name"] for c in categories]
        assert "authentication" in cat_names
        assert "export-formats" in cat_names
        assert "notifications" in cat_names

    def test_get_categories_count(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            categories = registry.get_categories()
        auth_cat = next(c for c in categories if c["name"] == "authentication")
        assert auth_cat["plugin_count"] == 1

    def test_get_plugin_details(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            details = registry.get_plugin_details("tokenade-oauth2")
        assert details is not None
        assert details["name"] == "tokenade-oauth2"
        assert details["category"] == "authentication"
        assert details["verified"] is True

    def test_get_plugin_details_not_found(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            details = registry.get_plugin_details("nonexistent")
        assert details is None

    def test_rate_plugin(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        assert registry.rate_plugin("tokenade-oauth2", 4.0, "Great plugin")
        ratings = registry.get_ratings("tokenade-oauth2")
        assert ratings["rating"] == 4.0
        assert ratings["review_count"] == 1
        assert ratings["reviews"][0]["review"] == "Great plugin"

    def test_rate_plugin_multiple(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        registry.rate_plugin("test", 4.0)
        registry.rate_plugin("test", 5.0)
        registry.rate_plugin("test", 3.0)
        ratings = registry.get_ratings("test")
        assert ratings["review_count"] == 3
        assert abs(ratings["rating"] - 4.0) < 0.1

    def test_rate_plugin_invalid_rating(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        assert not registry.rate_plugin("test", 0.5)
        assert not registry.rate_plugin("test", 6.0)

    def test_get_ratings_default(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        ratings = registry.get_ratings("nonexistent")
        assert ratings["rating"] == 0.0
        assert ratings["review_count"] == 0

    def test_increment_downloads(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        registry.increment_downloads("test-plugin")
        registry.increment_downloads("test-plugin")
        assert registry._local_downloads["test-plugin"] == 2

    def test_get_popular(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            popular = registry.get_popular(limit=2)
        assert len(popular) == 2
        assert popular[0]["downloads"] >= popular[1]["downloads"]

    def test_get_recent(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            recent = registry.get_recent(limit=2)
        assert len(recent) == 2

    def test_list_installed_empty(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        installed = registry.list_installed()
        assert len(installed) == 0

    def test_list_installed_with_plugin(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        plugin_dir = tmp_plugins_dir / "test-plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "description": "Test",
            "author": "test",
            "url": "",
            "type": "handler",
            "entry_point": "plugin.py",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        installed = registry.list_installed()
        assert len(installed) == 1
        assert installed[0].name == "test-plugin"


class TestPluginRegistryPersistence:
    """Test rating and download persistence."""

    def test_ratings_persist(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry1 = PluginRegistry(plugins_dir=tmp_plugins_dir)
        registry1.rate_plugin("test", 4.0)

        registry2 = PluginRegistry(plugins_dir=tmp_plugins_dir)
        ratings = registry2.get_ratings("test")
        assert ratings["rating"] == 4.0

    def test_downloads_persist(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry1 = PluginRegistry(plugins_dir=tmp_plugins_dir)
        registry1.increment_downloads("test")
        registry1.increment_downloads("test")

        registry2 = PluginRegistry(plugins_dir=tmp_plugins_dir)
        assert registry2._local_downloads["test"] == 2


# ─── PluginVerifier Tests ──────────────────────────────────────

class TestPluginVerifier:
    """Test SHA256 checksum verification."""

    def test_compute_sha256(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        test_file = tmp_plugins_dir / "test.txt"
        test_file.write_text("hello world")
        result = PluginVerifier._compute_sha256(test_file)
        assert len(result) == 64  # SHA256 hex digest length
        assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_verify_plugin_not_found(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)
        result = verifier.verify("nonexistent")
        assert not result.verified
        assert "not found" in result.errors[0].lower()

    def test_verify_no_checksums(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        plugin_dir = tmp_plugins_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{}")

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)
        result = verifier.verify("test-plugin")
        assert not result.verified
        assert "no checksum" in result.errors[0].lower()

    def test_verify_matching_checksums(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        plugin_dir = tmp_plugins_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('{"name": "test"}')
        (plugin_dir / "helper.py").write_text("# helper")

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)

        # Compute actual checksums
        checksums = verifier.compute_plugin_checksums("test-plugin")
        verifier.store_checksums("test-plugin", checksums)

        result = verifier.verify("test-plugin")
        assert result.verified
        assert result.checksums_mismatch == 0
        assert result.files_checked >= 2

    def test_verify_mismatched_checksums(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        plugin_dir = tmp_plugins_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('{"name": "test"}')

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)

        # Store wrong checksums
        verifier.store_checksums("test-plugin", {"plugin.json": "wrong_hash_value"})

        result = verifier.verify("test-plugin")
        assert not result.verified
        assert result.checksums_mismatch > 0

    def test_compute_plugin_checksums(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        plugin_dir = tmp_plugins_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{}")
        (plugin_dir / "module.py").write_text("# module")

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)
        checksums = verifier.compute_plugin_checksums("test-plugin")
        assert "plugin.json" in checksums
        assert "module.py" in checksums
        assert len(checksums["plugin.json"]) == 64

    def test_register_plugin(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        plugin_dir = tmp_plugins_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{}")

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)
        checksums = verifier.register_plugin("test-plugin")
        assert "plugin.json" in checksums

        # Now verify should pass
        result = verifier.verify("test-plugin")
        assert result.verified

    def test_verify_all(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        # Create two plugins
        for name in ["plugin-a", "plugin-b"]:
            pdir = tmp_plugins_dir / name
            pdir.mkdir()
            (pdir / "plugin.json").write_text("{}")

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)
        results = verifier.verify_all()
        assert len(results) == 2


# ─── PluginSearchIndex Tests ───────────────────────────────────

class TestPluginSearchIndex:
    """Test local TF-IDF search index."""

    def test_build_index(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index.build_index(sample_plugins)
        assert index._num_docs == 3

    def test_search_by_name(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index.build_index(sample_plugins)
        results = index.search("oauth2")
        assert len(results) >= 1
        assert results[0][0] == "tokenade-oauth2"

    def test_search_by_description(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index.build_index(sample_plugins)
        results = index.search("slack")
        assert len(results) >= 1
        assert any("slack" in r[2]["name"] for r in results)

    def test_search_by_tag(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index.build_index(sample_plugins)
        results = index.search("webhook")
        assert len(results) >= 1

    def test_search_by_author(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index.build_index(sample_plugins)
        results = index.search("community")
        assert len(results) >= 1

    def test_search_empty_query(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index.build_index(sample_plugins)
        results = index.search("")
        assert len(results) == 0

    def test_search_no_match(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index.build_index(sample_plugins)
        results = index.search("zzznonexistent")
        assert len(results) == 0

    def test_get_suggestions(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index.build_index(sample_plugins)
        suggestions = index.get_suggestions("token")
        assert len(suggestions) >= 1

    def test_get_suggestions_empty(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index.build_index(sample_plugins)
        suggestions = index.get_suggestions("zzznonexistent")
        assert len(suggestions) == 0

    def test_save_and_load(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index1 = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        index1.build_index(sample_plugins)
        index1.save()

        index2 = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        assert index2.load()
        results = index2.search("oauth2")
        assert len(results) >= 1

    def test_load_no_index(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_search import PluginSearchIndex

        index = PluginSearchIndex(plugins_dir=tmp_plugins_dir)
        assert not index.load()


# ─── PluginBrowser HTML Tests ──────────────────────────────────

class TestPluginBrowser:
    """Test static HTML marketplace page generation."""

    def test_generate_marketplace_html(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_browser import generate_marketplace_html
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        categories = [
            {"name": "authentication", "description": "Auth plugins", "icon": "auth", "plugin_count": 1},
            {"name": "export-formats", "description": "Export plugins", "icon": "export", "plugin_count": 1},
        ]

        output_path = str(tmp_plugins_dir / "marketplace.html")
        result = generate_marketplace_html(sample_plugins, categories, output_path)

        assert Path(result).exists()
        content = Path(result).read_text()
        assert "Tokenade Plugin Marketplace" in content
        assert "tokenade-oauth2" in content
        assert "tokenade-export-json" in content

    def test_generate_html_has_search(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_browser import generate_marketplace_html

        output_path = str(tmp_plugins_dir / "marketplace.html")
        generate_marketplace_html(sample_plugins, [], output_path)

        content = Path(output_path).read_text()
        assert "id=\"search\"" in content
        assert "id=\"plugins\"" in content

    def test_generate_html_empty_plugins(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_browser import generate_marketplace_html

        output_path = str(tmp_plugins_dir / "marketplace.html")
        result = generate_marketplace_html([], [], output_path)

        content = Path(result).read_text()
        assert "Tokenade Plugin Marketplace" in content

    def test_generate_html_creates_parent_dirs(self, tmp_plugins_dir, sample_plugins):
        from tokenade.core.integration.plugin_browser import generate_marketplace_html

        output_path = str(tmp_plugins_dir / "subdir" / "marketplace.html")
        result = generate_marketplace_html(sample_plugins, [], output_path)
        assert Path(result).exists()


# ─── CLI Command Tests ─────────────────────────────────────────

class TestPluginMarketplaceCLI:
    """Test CLI commands for plugin marketplace."""

    def test_plugin_search_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "search", "oauth2"])
        assert args.plugin_command == "search"
        assert args.query == "oauth2"

    def test_plugin_search_with_filters(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "search", "test", "--category", "auth", "--sort", "downloads"])
        assert args.query == "test"
        assert args.category == "auth"
        assert args.sort == "downloads"

    def test_plugin_categories_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "categories"])
        assert args.plugin_command == "categories"

    def test_plugin_popular_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "popular", "-n", "5"])
        assert args.plugin_command == "popular"
        assert args.limit == 5

    def test_plugin_recent_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "recent"])
        assert args.plugin_command == "recent"

    def test_plugin_rate_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "rate", "my-plugin", "4.5", "--review", "Great!"])
        assert args.plugin_command == "rate"
        assert args.name == "my-plugin"
        assert args.rating == 4.5
        assert args.review == "Great!"

    def test_plugin_verify_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "verify", "my-plugin"])
        assert args.plugin_command == "verify"
        assert args.name == "my-plugin"

    def test_plugin_verify_all_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "verify"])
        assert args.plugin_command == "verify"
        assert args.name is None

    def test_plugin_outdated_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "outdated"])
        assert args.plugin_command == "outdated"

    def test_plugin_browse_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["plugin", "browse", "-o", "/tmp/market.html"])
        assert args.plugin_command == "browse"
        assert args.output == "/tmp/market.html"

    def test_cmd_plugin_search(self, tmp_plugins_dir, sample_plugins, capsys):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        from tokenade.cli import _plugin_search

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            args = MagicMock(query="oauth2", plugin_type="", category="", tags=None, sort="rating")
            _plugin_search(registry, args)

        captured = capsys.readouterr()
        assert "tokenade-oauth2" in captured.out

    def test_cmd_plugin_categories(self, tmp_plugins_dir, sample_plugins, capsys):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        from tokenade.cli import _plugin_categories

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            _plugin_categories(registry)

        captured = capsys.readouterr()
        assert "authentication" in captured.out

    def test_cmd_plugin_popular(self, tmp_plugins_dir, sample_plugins, capsys):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        from tokenade.cli import _plugin_popular

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            args = MagicMock(limit=10)
            _plugin_popular(registry, args)

        captured = capsys.readouterr()
        assert "Popular" in captured.out

    def test_cmd_plugin_rate(self, tmp_plugins_dir, capsys):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        from tokenade.cli import _plugin_rate

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        args = MagicMock()
        args.name = "test-plugin"
        args.rating = 4.0
        args.review = "Good"
        _plugin_rate(registry, args)

        captured = capsys.readouterr()
        assert "4.0/5" in captured.out

    def test_cmd_plugin_rate_invalid(self, tmp_plugins_dir, capsys):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        from tokenade.cli import _plugin_rate

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        args = MagicMock(name="test", rating=0.5, review="")
        _plugin_rate(registry, args)

        captured = capsys.readouterr()
        assert "Failed" in captured.out

    def test_cmd_plugin_verify_empty(self, tmp_plugins_dir, capsys):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)
        results = verifier.verify_all()
        assert len(results) == 0

    def test_cmd_plugin_outdated_empty(self, tmp_plugins_dir, capsys):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        from tokenade.cli import _plugin_outdated

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, 'get_outdated', return_value=[]):
            _plugin_outdated(registry)

        captured = capsys.readouterr()
        assert "up to date" in captured.out

    def test_cmd_plugin_browse(self, tmp_plugins_dir, sample_plugins, capsys):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        from tokenade.cli import _plugin_browse

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        with patch.object(registry, '_fetch_registry', return_value=sample_plugins):
            output_path = str(tmp_plugins_dir / "market.html")
            args = MagicMock(output=output_path)
            _plugin_browse(registry, args)

        captured = capsys.readouterr()
        assert "generated" in captured.out
        assert Path(output_path).exists()


# ─── Enhanced Plugin CLI Tests ────────────────────────────────

class TestPluginCLIEnhanced:
    """Test enhanced plugin CLI: install checksums, info, list status, verify auto-register."""

    def test_install_registers_checksums(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        plugin_dir = tmp_plugins_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "test-plugin", "version": "1.0.0", "type": "session_refresh",
            "entry_point": "plugin.py", "description": "test",
        }))
        (plugin_dir / "plugin.py").write_text("class T: pass")

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)
        verifier.register_plugin("test-plugin")
        assert "test-plugin" in verifier._local_checksums
        assert len(verifier._local_checksums["test-plugin"]) == 2

    def test_verify_auto_registers(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        plugin_dir = tmp_plugins_dir / "new-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({"name": "new-plugin"}))
        (plugin_dir / "plugin.py").write_text("# plugin code")

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)
        result = verifier.verify("new-plugin")
        assert result.verified is False
        assert "No checksum data" in result.errors[0]

    def test_info_not_installed_in_registry(self, tmp_plugins_dir, capsys):
        from tokenade.core.integration.plugin_registry import PluginRegistry

        registry = PluginRegistry(plugins_dir=tmp_plugins_dir)
        plugin_meta = {"name": "remote-plugin", "version": "2.0.0", "type": "handler",
                       "author": "test", "description": "remote only", "dependencies": []}
        with patch.object(registry, 'get_plugin_details', return_value=plugin_meta):
            from tokenade.core.integration.plugin_loader import PluginLoader
            loader = PluginLoader(plugins_dir=tmp_plugins_dir)
            installed = loader.discover()
            assert not any(p["name"] == "remote-plugin" for p in installed)
            details = registry.get_plugin_details("remote-plugin")
            assert details is not None
            assert details["version"] == "2.0.0"

    def test_list_available_shows_install_status(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_registry import PluginRegistry
        from tokenade.core.integration.plugin_loader import PluginLoader

        loader = PluginLoader(plugins_dir=tmp_plugins_dir)
        plugin_dir = tmp_plugins_dir / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-plugin", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": "test",
        }))
        (plugin_dir / "plugin.py").write_text("class H: pass")

        installed = loader.discover()
        assert any(p["name"] == "my-plugin" for p in installed)

    def test_verify_all_auto_registers(self, tmp_plugins_dir):
        from tokenade.core.integration.plugin_verifier import PluginVerifier

        for name in ["plug-a", "plug-b"]:
            d = tmp_plugins_dir / name
            d.mkdir()
            (d / "plugin.json").write_text(json.dumps({"name": name}))
            (d / "plugin.py").write_text("# code")

        verifier = PluginVerifier(plugins_dir=tmp_plugins_dir)
        assert "plug-a" not in verifier._local_checksums
        assert "plug-b" not in verifier._local_checksums

        for name in ["plug-a", "plug-b"]:
            verifier.register_plugin(name)

        assert "plug-a" in verifier._local_checksums
        assert "plug-b" in verifier._local_checksums
        assert len(verifier._local_checksums["plug-a"]) == 2
