"""White-box tests for plugin_search.py — exercises every branch/path."""
from unittest.mock import patch

import pytest

from tokenade.core.integration.plugin_search import (
    PluginSearchIndex,
    _tokenize,
    _tf,
    _idf,
)


# ===================================================================
# _tokenize  (line 18-21)  — 4 branches
# ===================================================================

class TestTokenize:
    def test_normal_text(self):
        tokens = _tokenize("Hello World 123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "123" in tokens

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_short_tokens_filtered(self):
        tokens = _tokenize("a b cc ddd")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "cc" in tokens
        assert "ddd" in tokens

    def test_special_chars_only(self):
        assert _tokenize("!!!@@@###") == []


# ===================================================================
# _tf  (lines 24-28)  — 3 branches
# ===================================================================

class TestTf:
    def test_single_token(self):
        result = _tf(["hello"])
        assert result == {"hello": 1.0}

    def test_multiple_tokens(self):
        result = _tf(["a", "a", "b"])
        assert abs(result["a"] - 2 / 3) < 0.01
        assert abs(result["b"] - 1 / 3) < 0.01

    def test_empty_list(self):
        result = _tf([])
        assert result == {}  # total=1, empty Counter -> empty dict


# ===================================================================
# _idf  (lines 31-36)  — 3 branches
# ===================================================================

class TestIdf:
    def test_common_token(self):
        # df close to num_docs -> idf close to 1
        result = _idf({"common": 9}, 10)
        assert result["common"] < 1.5

    def test_rare_token(self):
        # df=1, num_docs=10 -> higher idf
        result = _idf({"rare": 1}, 10)
        assert result["rare"] > 2.0

    def test_zero_docs(self):
        # Edge case: num_docs=0 but df>0 (shouldn't happen in practice)
        result = _idf({"x": 0}, 0)
        assert "x" in result


# ===================================================================
# build_index  (lines 51-95)  — 5 branches
# ===================================================================

class TestBuildIndex:
    def test_empty_list(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx.build_index([])
        assert idx._num_docs == 0
        assert idx._documents == {}

    def test_normal_build(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx.build_index([
            {"name": "alpha", "description": "fast search", "author": "bob",
             "tags": ["speed", "search"]},
            {"name": "beta", "description": "slow tool", "author": "alice",
             "tags": ["utility"]},
        ])
        assert idx._num_docs == 2
        assert "alpha" in idx._documents
        assert "beta" in idx._documents

    def test_duplicate_names_overwrite(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx.build_index([
            {"name": "dup", "description": "first"},
            {"name": "dup", "description": "second"},
        ])
        assert idx._num_docs == 1
        assert "dup" in idx._documents

    def test_missing_fields_handled(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx.build_index([{"name": "minimal"}])
        assert idx._num_docs == 1
        meta = idx._documents["minimal"]["metadata"]
        assert meta["description"] == ""
        assert meta["author"] == ""
        assert meta["tags"] == []

    def test_rebuild_clears_old(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx.build_index([{"name": "old", "description": "old"}])
        assert "old" in idx._documents
        idx.build_index([{"name": "new", "description": "new"}])
        assert "old" not in idx._documents
        assert "new" in idx._documents
        assert idx._num_docs == 1


# ===================================================================
# search  (lines 97-125)  — 8 branches
# ===================================================================

class TestSearch:
    @pytest.fixture
    def built_index(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx.build_index([
            {"name": "search-tool", "description": "fast search engine",
             "author": "alice", "tags": ["search", "fast"], "verified": True},
            {"name": "other-thing", "description": "unrelated tool",
             "author": "bob", "tags": ["utility"]},
        ])
        return idx

    def test_empty_query_returns_empty(self, built_index):
        assert built_index.search("") == []
        assert built_index.search("a") == []  # single char -> no tokens

    def test_no_results(self, built_index):
        results = built_index.search("zzz_nonexistent")
        assert results == []

    def test_name_boost(self, built_index):
        results = built_index.search("search-tool")
        assert len(results) >= 1
        assert results[0][0] == "search-tool"
        assert results[0][1] > 2.0  # TF-IDF + 2.0 name boost

    def test_verified_boost(self, built_index):
        results = built_index.search("search")
        # search-tool is verified, should rank higher
        assert results[0][0] == "search-tool"

    def test_limit_respected(self, built_index):
        results = built_index.search("tool", limit=1)
        assert len(results) <= 1

    def test_multi_match_higher_score(self, built_index):
        results = built_index.search("fast search")
        assert len(results) >= 1
        # search-tool matches both "fast" and "search"
        assert results[0][0] == "search-tool"

    def test_score_ordering(self, built_index):
        results = built_index.search("tool")
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_special_char_query(self, built_index):
        assert built_index.search("!!!@@@") == []


# ===================================================================
# get_suggestions  (lines 127-136)  — 4 branches
# ===================================================================

class TestGetSuggestions:
    @pytest.fixture
    def idx(self, tmp_path):
        i = PluginSearchIndex(plugins_dir=tmp_path)
        i.build_index([
            {"name": "alpha-tool"},
            {"name": "alpha-search"},
            {"name": "beta-tool"},
        ])
        return i

    def test_partial_match(self, idx):
        results = idx.get_suggestions("alpha")
        assert len(results) == 2

    def test_no_match(self, idx):
        assert idx.get_suggestions("zzz") == []

    def test_limit(self, idx):
        results = idx.get_suggestions("a", limit=1)
        assert len(results) == 1

    def test_empty_input(self, idx):
        # Empty string matches everything (substring of all names)
        results = idx.get_suggestions("")
        assert len(results) == 3


# ===================================================================
# save / load  (lines 138-186)  — 5 branches
# ===================================================================

class TestSaveLoad:
    def test_round_trip(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx.build_index([
            {"name": "rt-plugin", "description": "round trip test",
             "author": "me", "tags": ["test"]},
        ])
        idx.save()
        assert idx._index_file.exists()

        idx2 = PluginSearchIndex(plugins_dir=tmp_path)
        assert idx2.load() is True
        assert idx2._num_docs == 1
        assert "rt-plugin" in idx2._documents

    def test_corrupt_file(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx._index_file.write_text("NOT JSON!!!")
        assert idx.load() is False

    def test_missing_file(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        assert idx.load() is False

    def test_os_error_on_save(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx.build_index([{"name": "x"}])
        with patch("builtins.open", side_effect=OSError("disk full")):
            idx.save()  # should not raise

    def test_save_empty_index(self, tmp_path):
        idx = PluginSearchIndex(plugins_dir=tmp_path)
        idx.build_index([])
        idx.save()
        idx2 = PluginSearchIndex(plugins_dir=tmp_path)
        assert idx2.load() is True
        assert idx2._num_docs == 0
