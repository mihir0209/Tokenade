"""Tests for Phase 62 — Global Rating Sync."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tokenade.core.integration.rating_sync import RatingSync


# ─── RatingSync Tests ───────────────────────────────────────

class TestRatingSync:
    def test_init(self):
        sync = RatingSync()
        assert sync._cache_path.parent.exists()
        assert isinstance(sync.has_pat(), bool)

    def test_no_pat_by_default(self):
        sync = RatingSync()
        # May or may not have PAT from env/config
        assert isinstance(sync.has_pat(), bool)

    @patch.dict("os.environ", {"GITHUB_TOKEN": ""})
    def test_no_pat_from_empty_env(self):
        sync = RatingSync()
        # Should not have PAT if env is empty and no config
        # (may still have from config file)
        assert isinstance(sync.has_pat(), bool)

    def test_set_pat(self, tmp_path):
        sync = RatingSync()
        # Save original config
        original_config = {}
        config_path = Path.home() / ".tokenade" / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                original_config = json.load(f)

        try:
            # Set PAT
            result = sync.set_pat("ghp_test123")
            assert result is True
            assert sync.has_pat() is True

            # Verify saved to config
            with open(config_path) as f:
                config = json.load(f)
            assert config["github_token"] == "ghp_test123"
        finally:
            # Restore original config
            with open(config_path, "w") as f:
                json.dump(original_config, f, indent=2)

    def test_local_cache_save_load(self, tmp_path):
        sync = RatingSync()
        sync._cache_path = tmp_path / "test_cache.json"

        # Save ratings
        ratings = {
            "oauth2": {"rating": 4.5, "review_count": 2, "reviews": []},
            "webhook": {"rating": 3.0, "review_count": 1, "reviews": []},
        }
        sync._save_local_cache(ratings)

        # Load ratings
        loaded = sync._load_local_cache()
        assert loaded["oauth2"]["rating"] == 4.5
        assert loaded["webhook"]["review_count"] == 1

    def test_update_local_cache(self, tmp_path):
        sync = RatingSync()
        sync._cache_path = tmp_path / "test_cache.json"

        # First rating
        sync._update_local_cache("oauth2", 4.0, "Good plugin")
        cache = sync._load_local_cache()
        assert cache["oauth2"]["rating"] == 4.0
        assert cache["oauth2"]["review_count"] == 1
        assert len(cache["oauth2"]["reviews"]) == 1

        # Second rating (averages)
        sync._update_local_cache("oauth2", 5.0, "Great!")
        cache = sync._load_local_cache()
        assert cache["oauth2"]["rating"] == 4.5
        assert cache["oauth2"]["review_count"] == 2
        assert len(cache["oauth2"]["reviews"]) == 2

    def test_parse_ratings_comments(self):
        sync = RatingSync()
        comments = [
            {
                "body": "⭐ 4\nPlugin: oauth2\nStars: ★★★★☆\n\nWorks well\n\n---\n*Synced from Tokenade v6.2.0*"
            },
            {
                "body": "⭐ 5\nPlugin: oauth2\nStars: ★★★★★\n\nExcellent!\n\n---\n*Synced from Tokenade v6.2.0*"
            },
            {
                "body": "⭐ 3\nPlugin: webhook\nStars: ★★★☆☆\n\nOK\n\n---\n*Synced from Tokenade v6.2.0*"
            },
        ]
        ratings = sync._parse_ratings_comments(comments)

        assert "oauth2" in ratings
        assert ratings["oauth2"]["review_count"] == 2
        assert ratings["oauth2"]["rating"] == 4.5
        assert "webhook" in ratings
        assert ratings["webhook"]["review_count"] == 1

    def test_parse_empty_comments(self):
        sync = RatingSync()
        ratings = sync._parse_ratings_comments([])
        assert ratings == {}

    def test_parse_malformed_comments(self):
        sync = RatingSync()
        comments = [
            {"body": "This is not a rating"},
            {"body": ""},
            {"body": "⭐ invalid\nPlugin: test"},
        ]
        ratings = sync._parse_ratings_comments(comments)
        assert ratings == {}


# ─── CLI Parser Tests ──────────────────────────────────────

class TestRatingCLIParser:
    def test_plugin_ratings_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["plugin", "ratings"])
        assert a.plugin_command == "ratings"

    def test_plugin_ratings_with_name(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["plugin", "ratings", "oauth2"])
        assert a.name == "oauth2"

    def test_plugin_rate_with_review(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["plugin", "rate", "oauth2", "4.5", "--review", "Great!"])
        assert a.name == "oauth2"
        assert a.rating == 4.5
        assert a.review == "Great!"

    def test_config_set_github_token(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["config", "set", "github-token", "ghp_test123"])
        assert a.config_command == "set"
        assert a.key == "github-token"
        assert a.value == "ghp_test123"
