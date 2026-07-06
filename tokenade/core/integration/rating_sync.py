"""
Global Rating Sync — sync plugin ratings via GitHub API.

Local ratings always work without any authentication.
If a GitHub PAT is configured, ratings are synced to the
mihir0209/tokenade-plugins repo via Issues API.

Usage:
    from tokenade.core.integration.rating_sync import RatingSync

    sync = RatingSync()
    sync.submit_rating("oauth2", 4.5, "Works great!")
    ratings = sync.get_global_ratings()
"""

import json
import logging

from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PLUGINS_REPO = "mihir0209/tokenade-plugins"
RATINGS_ISSUE_TITLE = "Plugin Ratings (Auto-synced)"
CONFIG_PATH = Path.home() / ".tokenade" / "config.json"


class RatingSync:
    """Sync plugin ratings to GitHub Issues API.

    Local ratings always work. Global sync requires a GitHub PAT.
    """

    def __init__(self):
        self._pat = self._load_pat()
        self._cache_path = Path.home() / ".tokenade" / "plugins" / ".global_ratings.json"
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_pat(self) -> Optional[str]:
        """Load GitHub PAT from config."""
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH) as f:
                    config = json.load(f)
                return config.get("github_token")
        except Exception:
            pass
        # Check env var
        import os
        return os.environ.get("GITHUB_TOKEN")

    def has_pat(self) -> bool:
        """Check if a GitHub PAT is configured."""
        return self._pat is not None and len(self._pat) > 0

    def set_pat(self, pat: str) -> bool:
        """Save GitHub PAT to config."""
        try:
            config = {}
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH) as f:
                    config = json.load(f)
            config["github_token"] = pat
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=2)
            self._pat = pat
            return True
        except Exception as e:
            logger.error(f"Failed to save PAT: {e}")
            return False

    def submit_rating(self, name: str, rating: float, review: str = "") -> bool:
        """Submit a rating globally (requires PAT).

        Args:
            name: Plugin name
            rating: Rating 1-5
            review: Optional review text

        Returns:
            True if synced successfully
        """
        if not self.has_pat():
            logger.warning("No GitHub PAT configured. Rating saved locally only.")
            return False

        try:
            import urllib.request
            import urllib.parse

            # Find or create the ratings issue
            issue_number = self._find_or_create_ratings_issue()
            if not issue_number:
                return False

            # Format the rating comment
            stars = "★" * int(rating) + "☆" * (5 - int(rating))
            body = f"⭐ {rating}\nPlugin: {name}\nStars: {stars}"
            if review:
                body += f"\n\n{review}"
            body += f"\n\n---\n*Synced from Tokenade v6.2.0*"

            # Post comment
            url = f"https://api.github.com/repos/{PLUGINS_REPO}/issues/{issue_number}/comments"
            data = json.dumps({"body": body}).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Authorization", f"token {self._pat}")
            req.add_header("Accept", "application/vnd.github.v3+json")
            req.add_header("Content-Type", "application/json")

            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 201:
                    logger.info(f"Rating synced to GitHub: {name} = {rating}")
                    # Update local cache
                    self._update_local_cache(name, rating, review)
                    return True

        except Exception as e:
            logger.error(f"Failed to sync rating: {e}")

        return False

    def get_global_ratings(self) -> Dict[str, Any]:
        """Get global ratings from GitHub (no PAT needed for reading).

        Returns:
            Dict mapping plugin names to rating data
        """
        try:
            import urllib.request

            # Try to get ratings from the issue comments
            issue_number = self._find_ratings_issue()
            if not issue_number:
                return self._load_local_cache()

            url = f"https://api.github.com/repos/{PLUGINS_REPO}/issues/{issue_number}/comments?per_page=100"
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/vnd.github.v3+json")

            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    comments = json.loads(resp.read().decode("utf-8"))
                    return self._parse_ratings_comments(comments)

        except Exception as e:
            logger.debug(f"Failed to fetch global ratings: {e}")

        return self._load_local_cache()

    def _find_ratings_issue(self) -> Optional[int]:
        """Find the ratings issue in the plugins repo."""
        try:
            import urllib.request

            url = f"https://api.github.com/repos/{PLUGINS_REPO}/issues?state=open&per_page=10"
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/vnd.github.v3+json")

            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    issues = json.loads(resp.read().decode("utf-8"))
                    for issue in issues:
                        if issue.get("title") == RATINGS_ISSUE_TITLE:
                            return issue["number"]
        except Exception:
            pass
        return None

    def _find_or_create_ratings_issue(self) -> Optional[int]:
        """Find or create the ratings issue."""
        existing = self._find_ratings_issue()
        if existing:
            return existing

        try:
            import urllib.request

            url = f"https://api.github.com/repos/{PLUGINS_REPO}/issues"
            data = json.dumps({
                "title": RATINGS_ISSUE_TITLE,
                "body": (
                    "This issue is auto-managed by Tokenade for plugin ratings.\n\n"
                    "Each comment represents a rating from a user.\n"
                    "Format: ⭐ <rating>\\nPlugin: <name>\\nStars: <stars>\\n\\n<review>"
                ),
                "labels": ["ratings"],
            }).encode("utf-8")

            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Authorization", f"token {self._pat}")
            req.add_header("Accept", "application/vnd.github.v3+json")
            req.add_header("Content-Type", "application/json")

            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 201:
                    result = json.loads(resp.read().decode("utf-8"))
                    return result["number"]
        except Exception as e:
            logger.error(f"Failed to create ratings issue: {e}")

        return None

    def _parse_ratings_comments(self, comments: List[Dict]) -> Dict[str, Any]:
        """Parse rating data from issue comments."""
        ratings = {}
        for comment in comments:
            body = comment.get("body", "")
            lines = body.split("\n")

            rating_val = None
            plugin_name = None
            review = ""

            for line in lines:
                if line.startswith("⭐"):
                    try:
                        rating_val = float(line.replace("⭐", "").strip())
                    except ValueError:
                        pass
                elif line.startswith("Plugin:"):
                    plugin_name = line.replace("Plugin:", "").strip()
                elif line.startswith("Stars:"):
                    pass  # Skip stars line
                elif not line.startswith("---") and not line.startswith("*Synced"):
                    if line.strip():
                        review = line.strip()

            if plugin_name and rating_val:
                if plugin_name not in ratings:
                    ratings[plugin_name] = {
                        "rating": rating_val,
                        "review_count": 1,
                        "reviews": [{"rating": rating_val, "review": review}],
                    }
                else:
                    entry = ratings[plugin_name]
                    old_total = entry["rating"] * entry["review_count"]
                    entry["review_count"] += 1
                    entry["rating"] = (old_total + rating_val) / entry["review_count"]
                    if review:
                        entry["reviews"].append({"rating": rating_val, "review": review})

        # Update local cache
        if ratings:
            self._save_local_cache(ratings)

        return ratings

    def _update_local_cache(self, name: str, rating: float, review: str):
        """Update local cache with a new rating."""
        cache = self._load_local_cache()
        if name not in cache:
            cache[name] = {
                "rating": rating,
                "review_count": 1,
                "reviews": [{"rating": rating, "review": review}],
            }
        else:
            entry = cache[name]
            old_total = entry["rating"] * entry["review_count"]
            entry["review_count"] += 1
            entry["rating"] = (old_total + rating) / entry["review_count"]
            if review:
                entry["reviews"].append({"rating": rating, "review": review})
        self._save_local_cache(cache)

    def _load_local_cache(self) -> Dict[str, Any]:
        """Load cached global ratings."""
        try:
            if self._cache_path.exists():
                with open(self._cache_path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_local_cache(self, ratings: Dict[str, Any]):
        """Save global ratings to local cache."""
        try:
            with open(self._cache_path, "w") as f:
                json.dump(ratings, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save ratings cache: {e}")
