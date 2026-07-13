"""White-box tests for plugin_browser.py and rating_sync.py."""
import json
from pathlib import Path

import pytest

from tokenade.core.integration.plugin_browser import generate_marketplace_html
from tokenade.core.integration.rating_sync import RatingSync


# ===================================================================
# plugin_browser — generate_marketplace_html  (lines 232-251)
# ===================================================================

class TestGenerateMarketplaceHtml:
    def test_generates_valid_html(self, tmp_path):
        out = tmp_path / "market.html"
        result = generate_marketplace_html(
            plugins=[], categories=[], output_path=str(out),
        )
        assert Path(result).exists()
        content = out.read_text()
        assert "<!DOCTYPE html>" in content
        assert "[]" in content  # plugins JSON

    def test_plugins_included(self, tmp_path):
        out = tmp_path / "market.html"
        plugins = [{"name": "test-plugin", "version": "1.0", "description": "A test"}]
        generate_marketplace_html(plugins=plugins, categories=[], output_path=str(out))
        content = out.read_text()
        assert "test-plugin" in content

    def test_categories_included(self, tmp_path):
        out = tmp_path / "market.html"
        cats = [{"name": "security", "icon": "🔐", "description": "Security plugins"}]
        generate_marketplace_html(plugins=[], categories=cats, output_path=str(out))
        content = out.read_text()
        assert "security" in content

    def test_custom_title(self, tmp_path):
        out = tmp_path / "market.html"
        generate_marketplace_html(
            plugins=[], categories=[], output_path=str(out),
            title="My Custom Marketplace",
        )
        content = out.read_text()
        assert "My Custom Marketplace" in content

    def test_html_escaped_title(self, tmp_path):
        out = tmp_path / "market.html"
        generate_marketplace_html(
            plugins=[], categories=[], output_path=str(out),
            title="My <b>Bold</b> Title",
        )
        content = out.read_text()
        assert "&lt;b&gt;Bold&lt;/b&gt;" in content

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "market.html"
        generate_marketplace_html(plugins=[], categories=[], output_path=str(out))
        assert out.exists()

    def test_plugins_with_ratings(self, tmp_path):
        out = tmp_path / "market.html"
        plugins = [{"name": "rated", "rating": 4.5, "review_count": 10, "downloads": 100}]
        generate_marketplace_html(plugins=plugins, categories=[], output_path=str(out))
        content = out.read_text()
        assert "rated" in content

    def test_empty_plugins_list(self, tmp_path):
        out = tmp_path / "market.html"
        generate_marketplace_html(plugins=[], categories=[], output_path=str(out))
        content = out.read_text()
        assert "TOKENADE_PLUGINS" not in content  # replaced with []


# ===================================================================
# rating_sync — RatingSync  (lines 29-286)
# ===================================================================

class TestRatingSync:
    @pytest.fixture
    def rs(self, tmp_path, monkeypatch):
        """RatingSync with home dir overridden to tmp_path."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        # Ensure config dir exists
        (tmp_path / ".tokenade").mkdir(exist_ok=True)
        return RatingSync()

    def test_no_pat_by_default(self, rs):
        assert rs.has_pat() is False

    def test_has_pat_when_set(self, rs):
        rs._pat = "ghp_test123"
        assert rs.has_pat() is True

    def test_has_pat_empty_string(self, rs):
        rs._pat = ""
        assert rs.has_pat() is False

    def test_submit_rating_without_pat(self, rs):
        result = rs.submit_rating("plugin", 4.0, "great")
        assert result is False

    def test_parse_ratings_comments_single(self, rs):
        comments = [{
            "body": "⭐ 4.5\nPlugin: my-plugin\nStars: ★★★★☆\n\nWorks well!\n\n---\n*Synced from Tokenade*"
        }]
        result = rs._parse_ratings_comments(comments)
        assert "my-plugin" in result
        assert result["my-plugin"]["rating"] == 4.5
        assert result["my-plugin"]["review_count"] == 1

    def test_parse_ratings_comments_multiple_same_plugin(self, rs):
        comments = [
            {"body": "⭐ 4.0\nPlugin: p\nStars: ★★★★☆\n\nGood\n\n---\n*Synced*"},
            {"body": "⭐ 5.0\nPlugin: p\nStars: ★★★★★\n\nGreat\n\n---\n*Synced*"},
        ]
        result = rs._parse_ratings_comments(comments)
        assert result["p"]["review_count"] == 2
        assert abs(result["p"]["rating"] - 4.5) < 0.01

    def test_parse_ratings_comments_malformed(self, rs):
        comments = [{"body": "random text without ratings"}]
        result = rs._parse_ratings_comments(comments)
        assert result == {}

    def test_parse_ratings_comments_no_review(self, rs):
        comments = [{"body": "⭐ 3.0\nPlugin: bare\nStars: ★★★☆☆\n\n---\n*Synced*"}]
        result = rs._parse_ratings_comments(comments)
        assert "bare" in result

    def test_local_cache_round_trip(self, rs):
        ratings = {"p1": {"rating": 4.0, "review_count": 1, "reviews": []}}
        rs._save_local_cache(ratings)
        loaded = rs._load_local_cache()
        assert loaded["p1"]["rating"] == 4.0

    def test_load_local_cache_missing(self, rs):
        assert rs._load_local_cache() == {}

    def test_load_local_cache_corrupt(self, rs):
        rs._cache_path.write_text("bad json!!!")
        assert rs._load_local_cache() == {}

    def test_update_local_cache_new(self, rs):
        rs._update_local_cache("new", 4.0, "nice")
        cache = rs._load_local_cache()
        assert cache["new"]["rating"] == 4.0
        assert cache["new"]["review_count"] == 1

    def test_update_local_cache_existing(self, rs):
        rs._update_local_cache("p", 4.0, "ok")
        rs._update_local_cache("p", 2.0, "meh")
        cache = rs._load_local_cache()
        assert cache["p"]["review_count"] == 2
        assert abs(cache["p"]["rating"] - 3.0) < 0.01

    def test_load_pat_from_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("GITHUB_TOKEN", "env_token_123")
        monkeypatch.setattr("tokenade.core.integration.rating_sync.CONFIG_PATH",
                            tmp_path / ".tokenade" / "config.json")
        rs = RatingSync()
        assert rs._pat == "env_token_123"

    def test_load_pat_from_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        config_path = tmp_path / ".tokenade" / "config.json"
        config_path.parent.mkdir(exist_ok=True)
        config_path.write_text(json.dumps({"github_token": "cfg_token"}))
        monkeypatch.setattr("tokenade.core.integration.rating_sync.CONFIG_PATH", config_path)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        rs = RatingSync()
        assert rs._pat == "cfg_token"
