"""White-box tests for plugin_registry.py — exercises every branch/path."""
import json
import time
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

from tokenade.core.integration.plugin_registry import (
    PluginRegistry,
    _version_lt,
    CATEGORIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plugin(name="test-plugin", version="1.0.0", type_="handler",
                 category="", tags=None, rating=0.0, review_count=0,
                 downloads=0, dependencies=None, min_version="",
                 max_version="", files=None, recent_downloads=None):
    """Build a registry-style plugin dict."""
    d = {
        "name": name, "version": version, "description": f"Desc for {name}",
        "author": "tester", "url": f"https://example.com/{name}",
        "type": type_, "entry_point": "plugin.py",
        "dependencies": dependencies or [], "category": category,
        "tags": tags or [], "rating": rating, "review_count": review_count,
        "downloads": downloads, "verified": False, "icon": "",
        "min_version": min_version, "max_version": max_version,
    }
    if files:
        d["files"] = files
    if recent_downloads is not None:
        d["recent_downloads"] = recent_downloads
    return d


def _write_cache(plugins_dir, plugins, timestamp=None):
    """Write a fresh registry cache file."""
    cache = {
        "timestamp": timestamp or time.time(),
        "plugins": plugins,
    }
    (plugins_dir / ".registry_cache.json").write_text(json.dumps(cache))


@pytest.fixture
def reg(tmp_path):
    """Create a PluginRegistry backed by tmp_path with no network."""
    return PluginRegistry(registry_url="https://example.com/reg", plugins_dir=tmp_path)


@pytest.fixture
def reg_cached(tmp_path):
    """Registry with a pre-populated cache."""
    plugins = [
        _make_plugin("alpha", version="1.0.0", category="security", tags=["auth", "oauth"]),
        _make_plugin("beta", version="2.1.0", category="validators", tags=["check"]),
        _make_plugin("gamma", version="0.9.0", type_="captcha", downloads=50),
        _make_plugin("delta", version="3.0.0", type_="proxy", rating=4.5, review_count=10),
    ]
    _write_cache(tmp_path, plugins)
    return PluginRegistry(registry_url="https://example.com/reg", plugins_dir=tmp_path)


# ===================================================================
# _version_lt  (lines 22-27)  — 5 branches
# ===================================================================

class TestVersionLt:
    def test_valid_lt(self):
        assert _version_lt("1.0.0", "2.0.0") is True

    def test_valid_gt(self):
        assert _version_lt("2.0.0", "1.0.0") is False

    def test_valid_eq(self):
        assert _version_lt("1.0.0", "1.0.0") is False

    def test_invalid_fallback_string_lt(self):
        assert _version_lt("abc", "def") is True

    def test_invalid_fallback_string_gt(self):
        assert _version_lt("def", "abc") is False


# ===================================================================
# _normalize_registry_url  (lines 87-113)  — 6 branches
# ===================================================================

class TestNormalizeRegistryUrl:
    def test_github_no_branch(self):
        url = PluginRegistry._normalize_registry_url("https://github.com/user/repo")
        assert url == "https://raw.githubusercontent.com/user/repo/main"

    def test_github_with_tree_branch(self):
        url = PluginRegistry._normalize_registry_url("https://github.com/user/repo/tree/develop")
        assert url == "https://raw.githubusercontent.com/user/repo/develop"

    def test_github_with_branch_and_path(self):
        url = PluginRegistry._normalize_registry_url("https://github.com/user/repo/tree/main/plugins")
        assert url == "https://raw.githubusercontent.com/user/repo/main/plugins"

    def test_github_blob_url(self):
        url = PluginRegistry._normalize_registry_url("https://github.com/user/repo/blob/main/file.py")
        assert url == "https://raw.githubusercontent.com/user/repo/main/file.py"

    def test_non_github_url_passthrough(self):
        url = PluginRegistry._normalize_registry_url("https://example.com/plugins")
        assert url == "https://example.com/plugins"

    def test_trailing_slash_stripped(self):
        url = PluginRegistry._normalize_registry_url("https://example.com/plugins/")
        assert url == "https://example.com/plugins"


# ===================================================================
# search — filter branches  (lines 127-148)  — 12 branches
# ===================================================================

class TestSearchFilters:
    def test_empty_query_returns_all(self, reg_cached):
        results = reg_cached.search(query="")
        assert len(results) == 4

    def test_query_matches_name(self, reg_cached):
        results = reg_cached.search(query="alpha")
        assert len(results) == 1 and results[0]["name"] == "alpha"

    def test_query_matches_description(self, reg_cached):
        results = reg_cached.search(query="Desc for beta")
        assert len(results) == 1 and results[0]["name"] == "beta"

    def test_query_matches_author(self, reg_cached):
        results = reg_cached.search(query="tester")
        assert len(results) == 4

    def test_query_matches_tag(self, reg_cached):
        results = reg_cached.search(query="oauth")
        assert len(results) == 1 and results[0]["name"] == "alpha"

    def test_query_no_match(self, reg_cached):
        results = reg_cached.search(query="zzz_nonexistent")
        assert results == []

    def test_plugin_type_filter(self, reg_cached):
        results = reg_cached.search(plugin_type="captcha")
        assert len(results) == 1 and results[0]["name"] == "gamma"

    def test_category_filter(self, reg_cached):
        results = reg_cached.search(category="security")
        assert len(results) == 1 and results[0]["name"] == "alpha"

    def test_tags_filter_intersection(self, reg_cached):
        results = reg_cached.search(tags=["check"])
        assert len(results) == 1 and results[0]["name"] == "beta"

    def test_tags_filter_no_intersection(self, reg_cached):
        results = reg_cached.search(tags=["nonexistent"])
        assert results == []

    def test_combined_filters(self, reg_cached):
        results = reg_cached.search(category="security", tags=["auth"])
        assert len(results) == 1 and results[0]["name"] == "alpha"

    def test_type_filter_no_match(self, reg_cached):
        results = reg_cached.search(plugin_type="notification")
        assert results == []


# ===================================================================
# search — sort branches  (lines 160-192)  — 6 branches
# ===================================================================

class TestSearchSorts:
    def test_sort_by_rating(self, reg_cached):
        results = reg_cached.search(sort_by="rating")
        names = [p["name"] for p in results]
        assert names[0] == "delta"  # rating=4.5

    def test_sort_by_downloads(self, reg_cached):
        results = reg_cached.search(sort_by="downloads")
        names = [p["name"] for p in results]
        assert names[0] == "gamma"  # downloads=50

    def test_sort_by_name(self, reg_cached):
        results = reg_cached.search(sort_by="name")
        names = [p["name"] for p in results]
        assert names == sorted(names)

    def test_sort_by_recent(self, reg_cached):
        # "recent" reverses the original insertion order from the cache
        by_recent = reg_cached.search(sort_by="recent")
        cache_plugins = json.loads((reg_cached.plugins_dir / ".registry_cache.json").read_text())["plugins"]
        cache_names = [p["name"] for p in cache_plugins]
        assert [p["name"] for p in by_recent] == list(reversed(cache_names))

    def test_sort_by_trending(self, tmp_path):
        now = time.time()
        plugins = [
            _make_plugin("hot", recent_downloads=[
                {"date": now - 1000, "count": 100},
                {"date": now - 700000, "count": 50},  # older than 7 days (604800s)
            ]),
            _make_plugin("cold", recent_downloads=[
                {"date": now - 700000, "count": 200},  # older than 7 days
            ]),
            _make_plugin("warm"),  # no recent_downloads
        ]
        _write_cache(tmp_path, plugins)
        r = PluginRegistry(registry_url="https://x", plugins_dir=tmp_path)
        results = r.search(sort_by="trending")
        assert results[0]["name"] == "hot"

    def test_trending_non_list_ignored(self, tmp_path):
        plugins = [
            _make_plugin("p1", recent_downloads="not-a-list"),
            _make_plugin("p2"),
        ]
        _write_cache(tmp_path, plugins)
        r = PluginRegistry(registry_url="https://x", plugins_dir=tmp_path)
        results = r.search(sort_by="trending")
        assert len(results) == 2

    def test_sort_unknown_fallback(self, reg_cached):
        results = reg_cached.search(sort_by="nonexistent_sort")
        names = [p["name"] for p in results]
        assert names == sorted(names)


# ===================================================================
# search — local ratings/downloads merge  (lines 150-157)  — 2 branches
# ===================================================================

class TestSearchLocalMerge:
    def test_local_ratings_merge(self, reg_cached):
        reg_cached._local_ratings["alpha"] = {"rating": 5.0, "review_count": 99, "reviews": []}
        results = reg_cached.search(query="alpha")
        assert results[0]["rating"] == 5.0
        assert results[0]["review_count"] == 99

    def test_local_downloads_merge(self, reg_cached):
        reg_cached._local_downloads["alpha"] = 1000
        results = reg_cached.search(query="alpha")
        assert results[0]["downloads"] == 0 + 1000  # registry 0 + local 1000


# ===================================================================
# check_compatibility  (lines 196-213)  — 6 branches
# ===================================================================

class TestCheckCompatibility:
    def test_plugin_not_found(self, reg_cached):
        result = reg_cached.check_compatibility("nonexistent")
        assert result["compatible"] is False
        assert "not found" in result["reason"].lower()

    def test_below_min_version(self, reg_cached):
        plugins = [
            _make_plugin("old-plugin", min_version="5.0.0"),
        ]
        _write_cache(reg_cached.plugins_dir, plugins)
        reg_cached._local_ratings = {}
        reg_cached._local_downloads = {}
        result = reg_cached.check_compatibility("old-plugin", "4.0.0")
        assert result["compatible"] is False
        assert "5.0.0" in result["reason"]

    def test_above_max_version(self, reg_cached):
        plugins = [
            _make_plugin("new-plugin", max_version="3.0.0"),
        ]
        _write_cache(reg_cached.plugins_dir, plugins)
        reg_cached._local_ratings = {}
        reg_cached._local_downloads = {}
        result = reg_cached.check_compatibility("new-plugin", "4.0.0")
        assert result["compatible"] is False
        assert "3.0.0" in result["reason"]

    def test_in_range(self, reg_cached):
        plugins = [
            _make_plugin("range-plugin", min_version="2.0.0", max_version="5.0.0"),
        ]
        _write_cache(reg_cached.plugins_dir, plugins)
        reg_cached._local_ratings = {}
        reg_cached._local_downloads = {}
        result = reg_cached.check_compatibility("range-plugin", "3.0.0")
        assert result["compatible"] is True

    def test_no_constraints(self, reg_cached):
        result = reg_cached.check_compatibility("alpha")
        assert result["compatible"] is True

    def test_invalid_version_strings(self, reg_cached):
        plugins = [
            _make_plugin("weird-plugin", min_version="not-a-version"),
        ]
        _write_cache(reg_cached.plugins_dir, plugins)
        reg_cached._local_ratings = {}
        reg_cached._local_downloads = {}
        result = reg_cached.check_compatibility("weird-plugin", "also-not")
        # Falls back to string comparison: "also-not" < "not-a-version" -> True -> below min
        assert result["compatible"] is False


# ===================================================================
# get_categories  (lines 215-239)  — 3 branches
# ===================================================================

class TestGetCategories:
    def test_no_other_category(self, reg_cached):
        cats = reg_cached.get_categories()
        names = [c["name"] for c in cats]
        assert "other" not in names
        assert len(cats) == len(CATEGORIES)

    def test_with_other_category(self, reg_cached):
        # Omit category key entirely so .get("category", "other") returns "other"
        plugin = _make_plugin("uncat")
        del plugin["category"]
        _write_cache(reg_cached.plugins_dir, [plugin])
        reg_cached._local_ratings = {}
        reg_cached._local_downloads = {}
        cats = reg_cached.get_categories()
        names = [c["name"] for c in cats]
        assert "other" in names
        other = next(c for c in cats if c["name"] == "other")
        assert other["plugin_count"] == 1

    def test_category_counts(self, reg_cached):
        cats = reg_cached.get_categories()
        sec = next(c for c in cats if c["name"] == "security")
        val = next(c for c in cats if c["name"] == "validators")
        assert sec["plugin_count"] == 1
        assert val["plugin_count"] == 1


# ===================================================================
# get_plugin_details  (lines 241-254)  — 4 branches
# ===================================================================

class TestGetPluginDetails:
    def test_found(self, reg_cached):
        result = reg_cached.get_plugin_details("alpha")
        assert result is not None
        assert result["name"] == "alpha"

    def test_not_found(self, reg_cached):
        result = reg_cached.get_plugin_details("nonexistent")
        assert result is None

    def test_local_ratings_merge(self, reg_cached):
        reg_cached._local_ratings["alpha"] = {"rating": 4.0, "review_count": 5, "reviews": [{"r": 1}]}
        result = reg_cached.get_plugin_details("alpha")
        assert result["rating"] == 4.0
        assert result["review_count"] == 5
        assert result["user_reviews"] == [{"r": 1}]

    def test_local_downloads_merge(self, reg_cached):
        reg_cached._local_downloads["alpha"] = 500
        result = reg_cached.get_plugin_details("alpha")
        assert result["downloads"] == 0 + 500


# ===================================================================
# rate_plugin  (lines 264-296)  — 6 branches
# ===================================================================

class TestRatePlugin:
    def test_invalid_rating_below(self, reg):
        assert reg.rate_plugin("x", 0.5) is False

    def test_invalid_rating_above(self, reg):
        assert reg.rate_plugin("x", 5.5) is False

    def test_first_rating_with_review(self, reg):
        assert reg.rate_plugin("x", 4.0, "great!") is True
        assert reg._local_ratings["x"]["rating"] == 4.0
        assert reg._local_ratings["x"]["review_count"] == 1
        assert len(reg._local_ratings["x"]["reviews"]) == 1

    def test_first_rating_without_review(self, reg):
        assert reg.rate_plugin("x", 3.0) is True
        assert reg._local_ratings["x"]["rating"] == 3.0
        assert len(reg._local_ratings["x"]["reviews"]) == 0

    def test_subsequent_rating_with_review(self, reg):
        reg.rate_plugin("x", 4.0)
        reg.rate_plugin("x", 2.0, "meh")
        entry = reg._local_ratings["x"]
        assert entry["review_count"] == 2
        assert abs(entry["rating"] - 3.0) < 0.01
        assert len(entry["reviews"]) == 1

    def test_subsequent_rating_without_review(self, reg):
        reg.rate_plugin("x", 4.0)
        reg.rate_plugin("x", 2.0)
        entry = reg._local_ratings["x"]
        assert entry["review_count"] == 2
        assert abs(entry["rating"] - 3.0) < 0.01
        assert len(entry["reviews"]) == 0


# ===================================================================
# get_ratings + increment_downloads  (lines 298-307)  — 4 branches
# ===================================================================

class TestGetRatingsAndDownloads:
    def test_get_ratings_has_local(self, reg):
        reg._local_ratings["x"] = {"rating": 4.5, "review_count": 3, "reviews": []}
        result = reg.get_ratings("x")
        assert result["rating"] == 4.5

    def test_get_ratings_no_local(self, reg):
        result = reg.get_ratings("nonexistent")
        assert result == {"rating": 0.0, "review_count": 0, "reviews": []}

    def test_increment_from_zero(self, reg):
        reg.increment_downloads("x")
        assert reg._local_downloads["x"] == 1

    def test_increment_from_existing(self, reg):
        reg._local_downloads["x"] = 5
        reg.increment_downloads("x")
        assert reg._local_downloads["x"] == 6


# ===================================================================
# install  (lines 309-348)  — 7 branches
# ===================================================================

class TestInstall:
    def test_plugin_not_found(self, reg):
        assert reg.install("nonexistent") is False

    def test_already_installed(self, reg_cached):
        (reg_cached.plugins_dir / "alpha").mkdir()
        assert reg_cached.install("alpha") is True

    def test_circular_dependency(self, reg):
        plugins = [_make_plugin("a", dependencies=["b"])]
        _write_cache(reg.plugins_dir, plugins)
        reg._local_ratings = {}
        reg._local_downloads = {}
        # Fake the chain to trigger circular detection
        assert reg.install("a", _install_chain=["b", "a"]) is False

    def test_missing_dependency_fails(self, reg):
        plugins = [
            _make_plugin("main-p", dependencies=["dep-missing"]),
        ]
        _write_cache(reg.plugins_dir, plugins)
        reg._local_ratings = {}
        reg._local_downloads = {}
        # dep-missing not in registry, so install fails
        assert reg.install("main-p") is False

    @patch.object(PluginRegistry, "_download_plugin", return_value=True)
    def test_successful_install(self, mock_dl, reg):
        plugins = [_make_plugin("new-plugin")]
        _write_cache(reg.plugins_dir, plugins)
        reg._local_ratings = {}
        reg._local_downloads = {}
        result = reg.install("new-plugin")
        assert result is True
        mock_dl.assert_called_once()

    @patch.object(PluginRegistry, "_download_plugin", return_value=True)
    def test_install_with_existing_deps(self, mock_dl, reg):
        (reg.plugins_dir / "existing-dep").mkdir()
        plugins = [_make_plugin("with-dep", dependencies=["existing-dep"])]
        _write_cache(reg.plugins_dir, plugins)
        reg._local_ratings = {}
        reg._local_downloads = {}
        result = reg.install("with-dep")
        assert result is True

    def test_install_chain_threading(self, reg):
        plugins = [_make_plugin("x")]
        _write_cache(reg.plugins_dir, plugins)
        reg._local_ratings = {}
        reg._local_downloads = {}
        chain = ["already-in-chain"]
        # Should add "x" to chain and proceed (will fail at download but chain is correct)
        reg.install("x", _install_chain=chain)
        assert "x" in chain


# ===================================================================
# uninstall  (lines 350-366)  — 3 branches
# ===================================================================

class TestUninstall:
    def test_not_installed(self, reg):
        assert reg.uninstall("nonexistent") is False

    @patch("shutil.rmtree")
    def test_no_dependents(self, mock_rmtree, reg):
        (reg.plugins_dir / "myplugin").mkdir()
        assert reg.uninstall("myplugin") is True
        mock_rmtree.assert_called_once()

    @patch("shutil.rmtree")
    def test_has_dependents_blocked(self, mock_rmtree, reg):
        (reg.plugins_dir / "base").mkdir()
        (reg.plugins_dir / "dependent").mkdir()
        # Write manifest for dependent so list_installed finds it
        (reg.plugins_dir / "dependent" / "plugin.json").write_text(json.dumps({
            "name": "dependent", "version": "1.0.0", "type": "handler",
            "entry_point": "p.py", "dependencies": ["base"],
        }))
        assert reg.uninstall("base") is False
        mock_rmtree.assert_not_called()


# ===================================================================
# list_installed  (lines 368-397)  — 6 branches
# ===================================================================

class TestListInstalled:
    def test_empty_dir(self, reg):
        result = reg.list_installed()
        assert result == []

    def test_valid_plugins(self, reg):
        d = reg.plugins_dir / "p1"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": "p1", "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "dependencies": ["dep1"],
            "category": "security", "tags": ["auth"],
        }))
        result = reg.list_installed()
        assert len(result) == 1
        assert result[0].name == "p1"
        assert result[0].dependencies == ["dep1"]
        assert result[0].category == "security"

    def test_hidden_dirs_skipped(self, reg):
        d = reg.plugins_dir / ".hidden"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({"name": ".hidden"}))
        assert reg.list_installed() == []

    def test_no_manifest_skipped(self, reg):
        d = reg.plugins_dir / "nomanifest"
        d.mkdir()
        assert reg.list_installed() == []

    def test_corrupt_json_skipped(self, reg, caplog):
        d = reg.plugins_dir / "corrupt"
        d.mkdir()
        (d / "plugin.json").write_text("NOT JSON!!!")
        import logging
        with caplog.at_level(logging.WARNING):
            result = reg.list_installed()
        assert result == []
        assert "Failed to load" in caplog.text

    def test_os_error_skipped(self, reg, caplog):
        d = reg.plugins_dir / "oserr"
        d.mkdir()
        manifest = d / "plugin.json"
        manifest.write_text(json.dumps(
            {"name": "oserr", "version": "1.0.0", "type": "handler", "entry_point": "p.py"}
        ))
        import logging
        with caplog.at_level(logging.WARNING):
            with patch("builtins.open", side_effect=OSError("disk full")):
                result = reg.list_installed()
        assert result == []


# ===================================================================
# get_outdated + update  (lines 399-441)  — 5 branches
# ===================================================================

class TestOutdatedAndUpdate:
    def test_all_up_to_date(self, reg_cached):
        # Install alpha locally with same version
        d = reg_cached.plugins_dir / "alpha"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": "alpha", "version": "1.0.0", "type": "handler", "entry_point": "p.py",
        }))
        outdated = reg_cached.get_outdated()
        assert outdated == []

    def test_some_outdated(self, reg_cached):
        d = reg_cached.plugins_dir / "alpha"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": "alpha", "version": "0.1.0", "type": "handler", "entry_point": "p.py",
        }))
        outdated = reg_cached.get_outdated()
        assert len(outdated) == 1
        assert outdated[0]["name"] == "alpha"
        assert outdated[0]["installed_version"] == "0.1.0"
        assert outdated[0]["available_version"] == "1.0.0"

    def test_not_in_registry(self, reg_cached):
        d = reg_cached.plugins_dir / "orphan"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": "orphan", "version": "1.0.0", "type": "handler", "entry_point": "p.py",
        }))
        outdated = reg_cached.get_outdated()
        assert outdated == []

    @patch.object(PluginRegistry, "_download_plugin", return_value=True)
    def test_update_specific_plugin(self, mock_dl, reg_cached):
        d = reg_cached.plugins_dir / "alpha"
        d.mkdir()
        (d / "plugin.json").write_text(json.dumps({
            "name": "alpha", "version": "0.1.0", "type": "handler", "entry_point": "p.py",
        }))
        with patch("shutil.rmtree"):
            count = reg_cached.update(plugin_name="alpha")
        assert count == 1

    @patch.object(PluginRegistry, "_download_plugin", return_value=True)
    def test_update_all(self, mock_dl, reg_cached):
        for name, ver in [("alpha", "0.1.0"), ("beta", "1.0.0")]:
            d = reg_cached.plugins_dir / name
            d.mkdir()
            (d / "plugin.json").write_text(json.dumps({
                "name": name, "version": ver, "type": "handler", "entry_point": "p.py",
            }))
        with patch("shutil.rmtree"):
            count = reg_cached.update()
        assert count == 2


# ===================================================================
# _fetch_registry  (lines 443-469)  — 10 branches
# ===================================================================

class TestFetchRegistry:
    def test_fresh_cache_hit(self, reg):
        _write_cache(reg.plugins_dir, [{"name": "cached"}], timestamp=time.time())
        result = reg._fetch_registry()
        assert result == [{"name": "cached"}]

    def test_stale_cache_network_success(self, reg):
        _write_cache(reg.plugins_dir, [{"name": "old"}], timestamp=time.time() - 7200)
        response = json.dumps([{"name": "fresh"}]).encode()
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = response
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = reg._fetch_registry()
        assert result == [{"name": "fresh"}]

    def test_stale_cache_network_fail(self, reg):
        _write_cache(reg.plugins_dir, [{"name": "old"}], timestamp=time.time() - 7200)
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = reg._fetch_registry()
        assert result == []

    def test_corrupt_cache_network_fail(self, reg):
        (reg.plugins_dir / ".registry_cache.json").write_text("NOT JSON!!!")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = reg._fetch_registry()
        assert result == []

    def test_no_cache_network_success(self, reg):
        response = json.dumps([{"name": "new"}]).encode()
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = response
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = reg._fetch_registry()
        assert result == [{"name": "new"}]
        assert reg._cache_file.exists()

    def test_no_cache_network_fail(self, reg):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = reg._fetch_registry()
        assert result == []

    def test_dict_response_format(self, reg):
        response = json.dumps({"plugins": [{"name": "in-dict"}]}).encode()
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = response
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = reg._fetch_registry()
        assert result == [{"name": "in-dict"}]

    def test_list_response_format(self, reg):
        response = json.dumps([{"name": "in-list"}]).encode()
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = response
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = reg._fetch_registry()
        assert result == [{"name": "in-list"}]

    def test_url_error(self, reg):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = reg._fetch_registry()
        assert result == []

    def test_json_decode_error(self, reg):
        response = b"not json"
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = response
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = reg._fetch_registry()
        assert result == []


# ===================================================================
# _download_plugin  (lines 471-506)  — 5 branches
# ===================================================================

class TestDownloadPlugin:
    @patch("urllib.request.urlopen")
    def test_all_files_success(self, mock_open, reg):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"file-content"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_resp
        plugin = _make_plugin("dl-test", files=["extra.txt"])
        result = reg._download_plugin(plugin)
        assert result is True
        assert (reg.plugins_dir / "dl-test" / "plugin.json").exists()

    @patch("urllib.request.urlopen")
    def test_plugin_json_fails(self, mock_open, reg):
        mock_resp_ok = MagicMock()
        mock_resp_ok.read.return_value = b"ok"
        mock_resp_ok.__enter__ = lambda s: s
        mock_resp_ok.__exit__ = MagicMock(return_value=False)
        mock_resp_err = MagicMock()
        mock_resp_err.__enter__ = MagicMock(side_effect=urllib.error.URLError("fail"))
        mock_resp_err.__exit__ = MagicMock(return_value=False)
        # First call fails (plugin.json), rest succeed
        mock_open.side_effect = [mock_resp_err, mock_resp_ok, mock_resp_ok]
        result = reg._download_plugin(_make_plugin("fail-json"))
        assert result is False

    @patch("urllib.request.urlopen")
    def test_plugin_py_fails(self, mock_open, reg):
        mock_resp_ok = MagicMock()
        mock_resp_ok.read.return_value = b"ok"
        mock_resp_ok.__enter__ = lambda s: s
        mock_resp_ok.__exit__ = MagicMock(return_value=False)
        mock_resp_err = MagicMock()
        mock_resp_err.__enter__ = MagicMock(side_effect=urllib.error.URLError("fail"))
        mock_resp_err.__exit__ = MagicMock(return_value=False)
        # plugin.json ok, plugin.py fails, site_config ok
        mock_open.side_effect = [mock_resp_ok, mock_resp_err, mock_resp_ok]
        result = reg._download_plugin(_make_plugin("fail-py"))
        assert result is False

    @patch("urllib.request.urlopen")
    def test_site_config_fails_skipped(self, mock_open, reg):
        mock_resp_ok = MagicMock()
        mock_resp_ok.read.return_value = b"ok"
        mock_resp_ok.__enter__ = lambda s: s
        mock_resp_ok.__exit__ = MagicMock(return_value=False)
        mock_resp_err = MagicMock()
        mock_resp_err.__enter__ = MagicMock(side_effect=urllib.error.URLError("fail"))
        mock_resp_err.__exit__ = MagicMock(return_value=False)
        # plugin.json ok, plugin.py ok, site_config fails
        mock_open.side_effect = [mock_resp_ok, mock_resp_ok, mock_resp_err]
        result = reg._download_plugin(_make_plugin("skip-config"))
        assert result is True

    @patch("urllib.request.urlopen")
    def test_extra_file_fails_skipped(self, mock_open, reg):
        mock_resp_ok = MagicMock()
        mock_resp_ok.read.return_value = b"ok"
        mock_resp_ok.__enter__ = lambda s: s
        mock_resp_ok.__exit__ = MagicMock(return_value=False)
        mock_resp_err = MagicMock()
        mock_resp_err.__enter__ = MagicMock(side_effect=urllib.error.URLError("fail"))
        mock_resp_err.__exit__ = MagicMock(return_value=False)
        # plugin.json ok, plugin.py ok, site_config ok, extra fails
        mock_open.side_effect = [mock_resp_ok, mock_resp_ok, mock_resp_ok, mock_resp_err]
        result = reg._download_plugin(_make_plugin("skip-extra", files=["extra.txt"]))
        assert result is True


# ===================================================================
# discover_from_url  (lines 508-585)  — 8 branches
# ===================================================================

class TestDiscoverFromUrl:
    def _make_response(self, data):
        """Create a mock urlopen response that returns JSON data."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_plugins_json_found(self, reg):
        plugins = [_make_plugin("from-plugins")]
        with patch("urllib.request.urlopen", return_value=self._make_response(plugins)):
            result = reg.discover_from_url("https://example.com/repo")
        assert len(result) == 1 and result[0]["name"] == "from-plugins"

    def test_marketplace_json_fallback(self, reg):
        def side_effect(req, **kw):
            url = req.full_url if hasattr(req, 'full_url') else str(req)
            if "plugins.json" in url:
                raise urllib.error.URLError("not found")
            return self._make_response({"plugins": [_make_plugin("from-market")]})
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = reg.discover_from_url("https://example.com/repo")
        assert len(result) == 1 and result[0]["name"] == "from-market"

    def test_all_tiers_fail(self, reg):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = reg.discover_from_url("https://example.com/repo")
        assert result == []

    def test_plugins_json_empty_falls_through(self, reg):
        def side_effect(req, **kw):
            url = req.full_url if hasattr(req, 'full_url') else str(req)
            if "plugins.json" in url:
                return self._make_response([])
            return self._make_response({"plugins": [_make_plugin("from-market")]})
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = reg.discover_from_url("https://example.com/repo")
        assert len(result) == 1

    def test_plugins_json_dict_format(self, reg):
        data = {"plugins": [_make_plugin("dict-format")]}
        with patch("urllib.request.urlopen", return_value=self._make_response(data)):
            result = reg.discover_from_url("https://example.com/repo")
        assert len(result) == 1 and result[0]["name"] == "dict-format"

    def test_non_raw_url_no_dir_scan(self, reg):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = reg.discover_from_url("https://example.com/not-github")
        assert result == []

    def test_raw_url_dir_scan_with_dirs(self, reg):
        dir_listing = [
            {"type": "dir", "name": "my-plugin",
             "download_url": "https://raw.githubusercontent.com/u/r/b/plugins/my-plugin/plugin.json"},
            {"type": "file", "name": "README.md"},
        ]
        plugin_meta = _make_plugin("my-plugin")

        def side_effect(req, **kw):
            url = req.full_url if hasattr(req, 'full_url') else str(req)
            if "plugins.json" in url or "marketplace.json" in url:
                raise urllib.error.URLError("not found")
            if "api.github.com" in url:
                return self._make_response(dir_listing)
            return self._make_response(plugin_meta)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = reg.discover_from_url("https://raw.githubusercontent.com/u/r/b/plugins")
        assert len(result) == 1

    def test_raw_url_scan_subdir_fails_continues(self, reg):
        dir_listing = [
            {"type": "dir", "name": "bad-plugin",
             "download_url": "https://raw.githubusercontent.com/u/r/b/plugins/bad-plugin/plugin.json"},
        ]

        def side_effect(req, **kw):
            url = req.full_url if hasattr(req, 'full_url') else str(req)
            if "plugins.json" in url or "marketplace.json" in url:
                raise urllib.error.URLError("not found")
            if "api.github.com" in url:
                return self._make_response(dir_listing)
            raise urllib.error.URLError("subdir fail")
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = reg.discover_from_url("https://raw.githubusercontent.com/u/r/b/plugins")
        assert result == []


# ===================================================================
# Persistence  (lines 587-621)  — 4 branches
# ===================================================================

class TestPersistence:
    def test_ratings_round_trip(self, reg):
        reg._local_ratings["x"] = {"rating": 4.0, "review_count": 2, "reviews": []}
        reg._save_local_ratings()
        loaded = reg._load_local_ratings()
        assert loaded["x"]["rating"] == 4.0

    def test_downloads_round_trip(self, reg):
        reg._local_downloads["x"] = 42
        reg._save_local_downloads()
        loaded = reg._load_local_downloads()
        assert loaded["x"] == 42

    def test_corrupt_ratings_file(self, reg):
        reg._ratings_file.write_text("NOT JSON!!!")
        assert reg._load_local_ratings() == {}

    def test_corrupt_downloads_file(self, reg):
        reg._downloads_file.write_text("NOT JSON!!!")
        assert reg._load_local_downloads() == {}
