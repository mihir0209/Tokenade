"""White-box tests for plugin_verifier.py — exercises every branch/path."""
import hashlib
import json

import pytest

from tokenade.core.integration.plugin_verifier import (
    PluginVerifier,
    VerificationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_plugin_file(base, name, content=b"file content"):
    """Write a file inside a plugin directory."""
    path = base / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def verifier(tmp_path):
    return PluginVerifier(plugins_dir=tmp_path)


@pytest.fixture
def plugin_with_files(tmp_path):
    """Create a plugin with known files and return (verifier, plugin_dir, checksums)."""
    v = PluginVerifier(plugins_dir=tmp_path)
    pd = tmp_path / "myplugin"
    pd.mkdir()
    (pd / "plugin.json").write_text('{"name":"myplugin"}')
    (pd / "plugin.py").write_text("x = 1")
    checksums = {
        "plugin.json": _sha256_of(b'{"name":"myplugin"}'),
        "plugin.py": _sha256_of(b"x = 1"),
    }
    return v, pd, checksums


# ===================================================================
# VerificationResult.summary  (lines 29-33)  — 3 branches
# ===================================================================

class TestVerificationResultSummary:
    def test_verified_summary(self):
        r = VerificationResult("p", True, 2, 2, 2, 0, [])
        assert "OK" in r.summary
        assert "2/2" in r.summary

    def test_failed_summary(self):
        r = VerificationResult("p", False, 2, 2, 1, 1, ["bad file"])
        assert "FAILED" in r.summary
        assert "1 checksum" in r.summary

    def test_verified_zero_files(self):
        r = VerificationResult("p", False, 0, 0, 0, 0, [])
        assert "FAILED" in r.summary


# ===================================================================
# _compute_sha256  (lines 168-175)  — 3 branches
# ===================================================================

class TestComputeSha256:
    def test_normal_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        result = PluginVerifier._compute_sha256(f)
        assert result == _sha256_of(b"hello world")

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        result = PluginVerifier._compute_sha256(f)
        assert result == _sha256_of(b"")

    def test_large_file(self, tmp_path):
        f = tmp_path / "large.bin"
        f.write_bytes(b"x" * 20000)  # > 8192 chunk size
        result = PluginVerifier._compute_sha256(f)
        assert result == _sha256_of(b"x" * 20000)


# ===================================================================
# verify  (lines 45-107)  — 6 branches
# ===================================================================

class TestVerify:
    def test_dir_not_found(self, verifier):
        result = verifier.verify("nonexistent")
        assert result.verified is False
        assert "not found" in result.errors[0].lower()

    def test_no_checksums(self, verifier, tmp_path):
        pd = tmp_path / "nochecksums"
        pd.mkdir()
        (pd / "plugin.json").write_text("{}")
        result = verifier.verify("nochecksums")
        assert result.verified is False
        assert "No checksum data" in result.errors[0]

    def test_all_match(self, plugin_with_files):
        v, pd, checksums = plugin_with_files
        v.store_checksums("myplugin", checksums)
        result = v.verify("myplugin")
        assert result.verified is True
        assert result.checksums_match == 2
        assert result.checksums_mismatch == 0

    def test_mismatch(self, plugin_with_files):
        v, pd, checksums = plugin_with_files
        v.store_checksums("myplugin", {"plugin.json": "wrong_hash"})
        result = v.verify("myplugin")
        assert result.verified is False
        assert result.checksums_mismatch >= 1

    def test_missing_file(self, plugin_with_files):
        v, pd, checksums = plugin_with_files
        v.store_checksums("myplugin", {"missing.txt": "abc123"})
        result = v.verify("myplugin")
        assert result.verified is False
        assert any("Missing file" in e for e in result.errors)

    def test_os_error_reading(self, plugin_with_files, monkeypatch):
        v, pd, checksums = plugin_with_files
        v.store_checksums("myplugin", checksums)
        real_open = open

        def boom(path, *a, **kw):
            if "plugin.json" in str(path) and "rb" in str(a):
                raise OSError("permission denied")
            return real_open(path, *a, **kw)
        monkeypatch.setattr("builtins.open", boom)
        result = v.verify("myplugin")
        assert result.verified is False
        assert any("permission denied" in e for e in result.errors)


# ===================================================================
# verify_all  (lines 109-117)  — 3 branches
# ===================================================================

class TestVerifyAll:
    def test_empty_dir(self, verifier):
        assert verifier.verify_all() == []

    def test_valid_plugin(self, plugin_with_files):
        v, pd, checksums = plugin_with_files
        v.store_checksums("myplugin", checksums)
        results = v.verify_all()
        assert len(results) == 1
        assert results[0].verified is True

    def test_hidden_dirs_skipped(self, verifier, tmp_path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "plugin.json").write_text("{}")
        assert verifier.verify_all() == []

    def test_non_dirs_skipped(self, verifier, tmp_path):
        (tmp_path / "file.txt").write_text("not a dir")
        assert verifier.verify_all() == []


# ===================================================================
# compute_plugin_checksums  (lines 124-139)  — 4 branches
# ===================================================================

class TestComputePluginChecksums:
    def test_normal(self, plugin_with_files):
        v, pd, _ = plugin_with_files
        cs = v.compute_plugin_checksums("myplugin")
        assert "plugin.json" in cs
        assert "plugin.py" in cs

    def test_empty_dir(self, verifier, tmp_path):
        (tmp_path / "empty").mkdir()
        cs = verifier.compute_plugin_checksums("empty")
        assert cs == {}

    def test_hidden_files_skipped(self, verifier, tmp_path):
        pd = tmp_path / "withhidden"
        pd.mkdir()
        (pd / "plugin.json").write_text("{}")
        (pd / ".env").write_text("secret")
        cs = verifier.compute_plugin_checksums("withhidden")
        assert ".env" not in cs
        assert "plugin.json" in cs

    def test_nonexistent_dir(self, verifier):
        cs = verifier.compute_plugin_checksums("nonexistent")
        assert cs == {}


# ===================================================================
# register_plugin  (lines 141-146)  — 3 branches
# ===================================================================

class TestRegisterPlugin:
    def test_normal(self, plugin_with_files):
        v, pd, _ = plugin_with_files
        cs = v.register_plugin("myplugin")
        assert "plugin.json" in cs
        assert "myplugin" in v._local_checksums

    def test_empty_checksums(self, verifier, tmp_path):
        (tmp_path / "empty_dir").mkdir()
        cs = verifier.register_plugin("empty_dir")
        assert cs == {}
        assert "empty_dir" not in verifier._local_checksums

    def test_overwrites_existing(self, plugin_with_files):
        v, pd, _ = plugin_with_files
        v.store_checksums("myplugin", {"old.txt": "old"})
        cs = v.register_plugin("myplugin")
        assert "plugin.json" in cs
        assert "old.txt" not in v._local_checksums["myplugin"]


# ===================================================================
# Persistence  (lines 177-193)  — 3 branches
# ===================================================================

class TestPersistence:
    def test_round_trip(self, verifier):
        verifier.store_checksums("x", {"a.py": "hash1"})
        v2 = PluginVerifier(plugins_dir=verifier.plugins_dir)
        assert "x" in v2._local_checksums
        assert v2._local_checksums["x"]["a.py"] == "hash1"

    def test_corrupt_file(self, verifier):
        verifier._checksums_file.write_text("NOT JSON!!!")
        v2 = PluginVerifier(plugins_dir=verifier.plugins_dir)
        assert v2._local_checksums == {}

    def test_os_error_on_save(self, verifier, monkeypatch):
        real_open = open

        def boom(path, *a, **kw):
            if ".checksums.json" in str(path) and "w" in str(kw.get("mode", "")):
                raise OSError("disk full")
            return real_open(path, *a, **kw)
        monkeypatch.setattr("builtins.open", boom)
        verifier.store_checksums("x", {"a": "b"})  # should not raise


# ===================================================================
# _get_expected_checksums  (lines 148-166)  — 3 branches
# ===================================================================

class TestGetExpectedChecksums:
    def test_local_checksums_priority(self, verifier):
        verifier._local_checksums["p"] = {"a.py": "local"}
        result = verifier._get_expected_checksums("p")
        assert result == {"a.py": "local"}

    def test_registry_cache_fallback(self, verifier, tmp_path):
        cache = {
            "plugins": [
                {"name": "cached-plugin", "checksums": {"b.py": "from_cache"}},
            ]
        }
        (tmp_path / ".registry_cache.json").write_text(json.dumps(cache))
        result = verifier._get_expected_checksums("cached-plugin")
        assert result == {"b.py": "from_cache"}

    def test_no_checksums_anywhere(self, verifier):
        result = verifier._get_expected_checksums("nonexistent")
        assert result == {}

    def test_corrupt_cache_falls_through(self, verifier, tmp_path):
        (tmp_path / ".registry_cache.json").write_text("bad json!!!")
        result = verifier._get_expected_checksums("p")
        assert result == {}
