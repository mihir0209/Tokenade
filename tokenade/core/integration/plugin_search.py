"""
Local TF-IDF search index for plugin marketplace.

Provides fast client-side search with relevance ranking.
"""

import json
import logging
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import Counter

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric, filter short tokens."""
    tokens = re.findall(r"[a-z0-9]{2,}", text.lower())
    return tokens


def _tf(tokens: List[str]) -> Dict[str, float]:
    """Term frequency for a document."""
    counts = Counter(tokens)
    total = len(tokens) if tokens else 1
    return {t: c / total for t, c in counts.items()}


def _idf(doc_freqs: Dict[str, int], num_docs: int) -> Dict[str, float]:
    """Inverse document frequency."""
    return {
        t: math.log((num_docs + 1) / (df + 1)) + 1
        for t, df in doc_freqs.items()
    }


class PluginSearchIndex:
    """TF-IDF search index for plugins."""

    def __init__(self, plugins_dir: Path = None):
        from tokenade.core.integration.plugin_registry import DEFAULT_PLUGINS_DIR
        self.plugins_dir = plugins_dir or DEFAULT_PLUGINS_DIR
        self._index_file = self.plugins_dir / ".search_index.json"
        self._documents: Dict[str, Dict] = {}
        self._idf: Dict[str, float] = {}
        self._doc_freqs: Dict[str, int] = {}
        self._num_docs = 0

    def build_index(self, plugins: List[Dict]) -> None:
        """Build search index from plugin metadata."""
        self._documents.clear()
        self._doc_freqs.clear()

        for plugin in plugins:
            name = plugin.get("name", "")
            # Combine all searchable fields
            text = " ".join([
                name,
                plugin.get("description", ""),
                plugin.get("author", ""),
                plugin.get("category", ""),
                " ".join(plugin.get("tags", [])),
            ])
            tokens = _tokenize(text)
            self._documents[name] = {
                "tokens": tokens,
                "tf": _tf(tokens),
                "metadata": {
                    "name": name,
                    "version": plugin.get("version", ""),
                    "description": plugin.get("description", ""),
                    "author": plugin.get("author", ""),
                    "category": plugin.get("category", ""),
                    "tags": plugin.get("tags", []),
                    "rating": plugin.get("rating", 0),
                    "downloads": plugin.get("downloads", 0),
                },
            }
            # Update document frequencies
            unique_tokens = set(tokens)
            for t in unique_tokens:
                self._doc_freqs[t] = self._doc_freqs.get(t, 0) + 1

        self._num_docs = len(self._documents)
        self._idf = _idf(self._doc_freqs, self._num_docs)

        # Score all documents for each token
        for name, doc in self._documents.items():
            scores = {}
            for t, tf_val in doc["tf"].items():
                idf_val = self._idf.get(t, 1.0)
                scores[t] = tf_val * idf_val
            doc["scores"] = scores

    def search(self, query: str, limit: int = 20) -> List[Tuple[str, float, Dict]]:
        """Search plugins by query. Returns list of (name, score, metadata)."""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        results = []
        for name, doc in self._documents.items():
            score = 0.0
            for qt in query_tokens:
                score += doc["scores"].get(qt, 0.0)

            if score <= 0:
                continue

            # Boost exact name matches
            if query.lower() in name.lower():
                score += 2.0

            # Boost by rating and downloads
            meta = doc["metadata"]
            score += meta.get("rating", 0) * 0.05
            score += min(math.log(meta.get("downloads", 0) + 1) * 0.1, 1.0)

            if score > 0:
                results.append((name, score, meta))

        results.sort(key=lambda x: -x[1])
        return results[:limit]

    def get_suggestions(self, partial: str, limit: int = 10) -> List[str]:
        """Get autocomplete suggestions for a partial query."""
        partial_lower = partial.lower()
        suggestions = []
        for name in self._documents:
            if partial_lower in name.lower():
                suggestions.append(name)
            if len(suggestions) >= limit:
                break
        return suggestions

    def save(self) -> None:
        """Save index to disk."""
        data = {
            "num_docs": self._num_docs,
            "idf": self._idf,
            "doc_freqs": self._doc_freqs,
            "documents": {
                name: {
                    "tf": doc["tf"],
                    "metadata": doc["metadata"],
                }
                for name, doc in self._documents.items()
            },
        }
        try:
            with open(self._index_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save search index: {e}")

    def load(self) -> bool:
        """Load index from disk."""
        if not self._index_file.exists():
            return False
        try:
            with open(self._index_file, "r") as f:
                data = json.load(f)
            self._num_docs = data["num_docs"]
            self._idf = data["idf"]
            self._doc_freqs = data["doc_freqs"]
            self._documents = {}
            for name, doc_data in data["documents"].items():
                tokens = []
                for t, count in doc_data["tf"].items():
                    tokens.extend([t] * max(1, int(count * 100)))
                scores = {}
                for t, tf_val in doc_data["tf"].items():
                    idf_val = self._idf.get(t, 1.0)
                    scores[t] = tf_val * idf_val
                self._documents[name] = {
                    "tokens": tokens,
                    "tf": doc_data["tf"],
                    "metadata": doc_data["metadata"],
                    "scores": scores,
                }
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load search index: {e}")
            return False
