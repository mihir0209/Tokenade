"""Tests for Chrome Binary Patcher (Phase 28)."""
import os
import stat
import tempfile

import pytest

from tokenade.core.browser.patcher import ChromePatcher, PatchResult, CDC_PATTERN, CDC_REPLACEMENT_TEMPLATE


class TestCDCPattern:
    """Tests for the cdc_ regex pattern."""

    def test_pattern_matches_standard_cdc(self):
        data = b"{window.cdc_asdjflasutopfhvcZLmcfl_Array = 1;}"
        assert CDC_PATTERN.search(data) is not None

    def test_pattern_matches_cdc_with_underscore(self):
        data = b"{window.cdc_adoQpoasnfa76pfcZLmcfl_Promise = 1;}"
        assert CDC_PATTERN.search(data) is not None

    def test_pattern_matches_cdc_with_space(self):
        data = b"{window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol = 1;}"
        assert CDC_PATTERN.search(data) is not None

    def test_pattern_matches_short_cdc(self):
        data = b"{window.cdc_test = 1;}"
        assert CDC_PATTERN.search(data) is not None

    def test_pattern_no_match_without_window(self):
        data = b"cdc_adoQpoasnfa76pfcZLmcfl_Array"
        assert CDC_PATTERN.search(data) is None

    def test_pattern_no_match_without_braces(self):
        data = b"window.cdc_adoQpoasnfa76pfcZLmcfl_Array = 1;"
        assert CDC_PATTERN.search(data) is None

    def test_pattern_matches_in_binary_content(self):
        data = b"\x00\x00{window.cdc_adoQpoasnfa76pfcZLmcfl_Array = 1;}\x00\x00"
        match = CDC_PATTERN.search(data)
        assert match is not None
        assert match.group().startswith(b"{window.cdc")

    def test_pattern_multiple_matches(self):
        data = b"{window.cdc_Array = 1;} padding {window.cdc_Promise = 2;}"
        matches = list(CDC_PATTERN.finditer(data))
        assert len(matches) == 2


class TestChromePatcherInit:
    """Tests for ChromePatcher initialization."""

    def test_init(self):
        patcher = ChromePatcher()
        assert patcher is not None


class TestFindBrowserBinary:
    """Tests for browser binary discovery."""

    def test_find_chrome(self):
        patcher = ChromePatcher()
        result = patcher.find_browser_binary("chrome")
        # May or may not find chrome on CI, just check it returns str or None
        assert result is None or isinstance(result, str)

    def test_find_chromium(self):
        patcher = ChromePatcher()
        result = patcher.find_browser_binary("chromium")
        assert result is None or isinstance(result, str)

    def test_find_brave(self):
        patcher = ChromePatcher()
        result = patcher.find_browser_binary("brave")
        assert result is None or isinstance(result, str)

    def test_find_unknown_browser(self):
        patcher = ChromePatcher()
        result = patcher.find_browser_binary("nonexistent_browser_xyz")
        assert result is None


class TestScan:
    """Tests for binary scanning."""

    def test_scan_nonexistent_file(self):
        patcher = ChromePatcher()
        result = patcher.scan("/nonexistent/path/to/chrome")
        assert "error" in result
        assert result["matches"] == []

    def test_scan_clean_binary(self, tmp_path):
        binary = tmp_path / "chrome"
        binary.write_bytes(b"ELF binary content here no cdc stuff")
        patcher = ChromePatcher()
        result = patcher.scan(str(binary))
        assert result["patchable"] is False
        assert len(result["matches"]) == 0

    def test_scan_dirty_binary(self, tmp_path):
        content = b"\x7fELF" + b"\x00" * 100 + b"{window.cdc_adoQpoasnfa76pfcZLmcfl_Array = document.createElement('div');}" + b"\x00" * 100
        binary = tmp_path / "chrome"
        binary.write_bytes(content)
        patcher = ChromePatcher()
        result = patcher.scan(str(binary))
        assert result["patchable"] is True
        assert len(result["matches"]) == 1
        assert result["matches"][0]["length"] > 0

    def test_scan_binary_with_multiple_cdc(self, tmp_path):
        content = (
            b"{window.cdc_Array = 1;}"
            b"some padding"
            b"{window.cdc_Promise = 2;}"
        )
        binary = tmp_path / "chrome"
        binary.write_bytes(content)
        patcher = ChromePatcher()
        result = patcher.scan(str(binary))
        assert result["patchable"] is True
        assert len(result["matches"]) == 2

    def test_scan_returns_size(self, tmp_path):
        binary = tmp_path / "chrome"
        binary.write_bytes(b"test content")
        patcher = ChromePatcher()
        result = patcher.scan(str(binary))
        assert result["size"] == len(b"test content")


class TestMakeReplacement:
    """Tests for replacement byte generation."""

    def test_replacement_same_length(self):
        patcher = ChromePatcher()
        for length in [20, 30, 50, 70]:
            replacement = patcher._make_replacement(length)
            assert len(replacement) == length

    def test_replacement_starts_with_template(self):
        patcher = ChromePatcher()
        replacement = patcher._make_replacement(50)
        assert replacement.startswith(CDC_REPLACEMENT_TEMPLATE)

    def test_replacement_padded_with_spaces(self):
        patcher = ChromePatcher()
        replacement = patcher._make_replacement(50)
        assert replacement.endswith(b" " * (50 - len(CDC_REPLACEMENT_TEMPLATE)))

    def test_replacement_truncated_if_too_short(self):
        patcher = ChromePatcher()
        replacement = patcher._make_replacement(5)
        assert len(replacement) == 5
        assert replacement == CDC_REPLACEMENT_TEMPLATE[:5]


class TestPatch:
    """Tests for binary patching."""

    def test_patch_nonexistent_file(self):
        patcher = ChromePatcher()
        result = patcher.patch("/nonexistent/chrome")
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_patch_clean_binary(self, tmp_path):
        binary = tmp_path / "chrome"
        binary.write_bytes(b"clean binary no cdc here")
        patcher = ChromePatcher()
        result = patcher.patch(str(binary))
        assert result.success is False
        assert "no cdc" in result.error.lower()

    def test_patch_dirty_binary(self, tmp_path):
        original_content = b"\x7fELF" + b"\x00" * 100 + b"{window.cdc_adoQpoasnfa76pfcZLmcfl_Array = document.createElement('div');}" + b"\x00" * 100
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)

        patcher = ChromePatcher()
        result = patcher.patch(str(binary))

        assert result.success is True
        assert result.patches_applied == 1
        assert result.patched_path is not None
        assert os.path.isfile(result.patched_path)

        # Verify patched binary has no cdc_
        patched_content = open(result.patched_path, "rb").read()
        assert b"cdc_" not in patched_content
        # Verify size unchanged
        assert len(patched_content) == len(original_content)

    def test_patch_creates_backup(self, tmp_path):
        original_content = b"{window.cdc_test = 1;}"
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)

        patcher = ChromePatcher()
        result = patcher.patch(str(binary))

        assert result.success is True
        assert result.backup_path is not None
        assert os.path.isfile(result.backup_path)
        # Backup should be identical to original
        assert open(result.backup_path, "rb").read() == original_content

    def test_patch_no_backup(self, tmp_path):
        original_content = b"{window.cdc_test = 1;}"
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)

        patcher = ChromePatcher()
        result = patcher.patch(str(binary), backup=False)

        assert result.success is True
        assert result.backup_path is None
        assert not os.path.isfile(str(binary) + ".backup")

    def test_patch_custom_output_path(self, tmp_path):
        original_content = b"{window.cdc_test = 1;}"
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)
        output = tmp_path / "patched_chrome"

        patcher = ChromePatcher()
        result = patcher.patch(str(binary), output_path=str(output))

        assert result.success is True
        assert result.patched_path == str(output)
        assert os.path.isfile(str(output))

    def test_patch_preserves_permissions(self, tmp_path):
        original_content = b"{window.cdc_test = 1;}"
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)
        os.chmod(str(binary), 0o755)

        patcher = ChromePatcher()
        result = patcher.patch(str(binary))

        assert result.success is True
        patched_mode = os.stat(result.patched_path).st_mode
        assert patched_mode & stat.S_IXUSR  # User execute bit

    def test_patch_multiple_cdc(self, tmp_path):
        original_content = (
            b"prefix"
            b"{window.cdc_Array = 1;}"
            b"middle"
            b"{window.cdc_Promise = 2;}"
            b"suffix"
        )
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)

        patcher = ChromePatcher()
        result = patcher.patch(str(binary))

        assert result.success is True
        assert result.patches_applied == 2

        patched_content = open(result.patched_path, "rb").read()
        assert b"cdc_" not in patched_content

    def test_patch_preserves_non_cdc_content(self, tmp_path):
        original_content = b"ELF header" + b"\x00" * 50 + b"{window.cdc_test = 1;}" + b"\x00" * 50 + b"more binary data"
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)

        patcher = ChromePatcher()
        result = patcher.patch(str(binary))

        patched_content = open(result.patched_path, "rb").read()
        assert patched_content.startswith(b"ELF header")
        assert b"more binary data" in patched_content

    def test_patch_size_unchanged(self, tmp_path):
        # Create content of specific size
        original_content = b"\x00" * 1000 + b"{window.cdc_test = 1;}" + b"\x00" * 1000
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)

        patcher = ChromePatcher()
        result = patcher.patch(str(binary))

        patched_content = open(result.patched_path, "rb").read()
        assert len(patched_content) == len(original_content)

    def test_patch_default_output_is_patched_suffix(self, tmp_path):
        original_content = b"{window.cdc_test = 1;}"
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)

        patcher = ChromePatcher()
        result = patcher.patch(str(binary))

        assert result.patched_path == str(binary) + ".patched"


class TestRestore:
    """Tests for binary restoration."""

    def test_restore_with_backup(self, tmp_path):
        original_content = b"{window.cdc_test = 1;}"
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)

        patcher = ChromePatcher()
        patcher.patch(str(binary))

        # Modify the original (simulate corruption)
        binary.write_bytes(b"corrupted")
        assert binary.read_bytes() == b"corrupted"

        # Restore
        assert patcher.restore(str(binary)) is True
        assert binary.read_bytes() == original_content

    def test_restore_without_backup(self, tmp_path):
        binary = tmp_path / "chrome"
        binary.write_bytes(b"test content")

        patcher = ChromePatcher()
        assert patcher.restore(str(binary)) is False


class TestVerify:
    """Tests for patch verification."""

    def test_verify_clean_binary(self, tmp_path):
        binary = tmp_path / "chrome"
        binary.write_bytes(b"clean binary")

        patcher = ChromePatcher()
        result = patcher.verify(str(binary))
        assert result["patched"] is True
        assert result["has_backup"] is False
        assert result["remaining_artifacts"] == 0

    def test_verify_dirty_binary(self, tmp_path):
        binary = tmp_path / "chrome"
        binary.write_bytes(b"{window.cdc_test = 1;}")

        patcher = ChromePatcher()
        result = patcher.verify(str(binary))
        assert result["patched"] is False
        assert result["remaining_artifacts"] == 1

    def test_verify_patched_binary(self, tmp_path):
        binary = tmp_path / "chrome"
        binary.write_bytes(b"{window.cdc_test = 1;}")

        patcher = ChromePatcher()
        patcher.patch(str(binary))

        result = patcher.verify(str(binary))
        assert result["patched"] is True
        assert result["has_backup"] is True
        assert result["has_patched_variant"] is True


class TestPatchResult:
    """Tests for PatchResult dataclass."""

    def test_success_summary(self):
        result = PatchResult(
            success=True,
            original_path="/usr/bin/chrome",
            patched_path="/usr/bin/chrome.patched",
            patches_applied=3,
        )
        assert "Patched 3" in result.summary
        assert "/usr/bin/chrome.patched" in result.summary

    def test_failure_summary(self):
        result = PatchResult(
            success=False,
            original_path="/usr/bin/chrome",
            error="File not found",
        )
        assert "failed" in result.summary.lower()
        assert "File not found" in result.summary


class TestPatchCLIMode:
    """Tests for CLI-level patch operations."""

    def test_patch_idempotent(self, tmp_path):
        """Patching twice should not break anything."""
        original_content = b"\x00" * 50 + b"{window.cdc_test = 1;}" + b"\x00" * 50
        binary = tmp_path / "chrome"
        binary.write_bytes(original_content)

        patcher = ChromePatcher()
        result1 = patcher.patch(str(binary))
        assert result1.success is True

        # Patch again — should find no cdc_ in original (it's unchanged)
        # but the patched version exists
        result2 = patcher.patch(str(binary))
        assert result2.success is True

    def test_scan_then_patch(self, tmp_path):
        """Scan first, then patch."""
        content = b"\x00" * 50 + b"{window.cdc_adoQpoasnfa76pfcZLmcfl_Array = 1;}" + b"\x00" * 50
        binary = tmp_path / "chrome"
        binary.write_bytes(content)

        patcher = ChromePatcher()

        # Scan
        scan = patcher.scan(str(binary))
        assert scan["patchable"] is True
        assert len(scan["matches"]) == 1

        # Patch
        result = patcher.patch(str(binary))
        assert result.success is True

        # Verify
        verify = patcher.verify(str(binary))
        assert verify["patched"] is True
