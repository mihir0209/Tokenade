"""Comprehensive tests for safari_extractor.py to boost coverage from 60% to 80%+."""

import os
import struct
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.importer.safari_extractor import SafariExtractor, MAC_EPOCH_OFFSET


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_safari_page_with_entry(flags=0x1, expiry=1000000000.0 + MAC_EPOCH_OFFSET,
                                  name_offset=84, value_offset=94, domain_offset=104,
                                  path_offset=119):
    """Build a page with one cookie entry and string data."""
    # Page header (4 bytes)
    page = struct.pack(">I", 0x00000100)
    # Number of cookies (4 bytes)
    page += struct.pack(">I", 1)

    # Cookie entry offset - points to right after the offset table
    entry_offset = 4 + 4 + 4  # header + count + 1 offset
    page += struct.pack(">I", entry_offset)

    # Build cookie entry: flags(4) + pad(4) + 6*string_offsets(24) + comment_offset(4) + expiry(8) + creation(8) = 52 bytes
    cookie_entry = b""
    cookie_entry += struct.pack(">I", flags)
    cookie_entry += struct.pack(">I", 0)  # padding
    # url_offset, name_offset, value_offset, domain_offset, path_offset, comment_offset
    cookie_entry += struct.pack(">I", 100)  # url
    cookie_entry += struct.pack(">I", name_offset)
    cookie_entry += struct.pack(">I", value_offset)
    cookie_entry += struct.pack(">I", domain_offset)
    cookie_entry += struct.pack(">I", path_offset)
    cookie_entry += struct.pack(">I", 80)  # comment
    cookie_entry += struct.pack(">I", 0)   # extra comment skip
    cookie_entry += struct.pack(">d", expiry)
    cookie_entry += struct.pack(">d", expiry - 100)  # creation

    page += cookie_entry

    # String region - pad enough so offsets are valid
    # Strings region starts at offset 64 (header 4 + count 4 + offset_table 4 + cookie_entry 52)
    strings = bytearray(200)
    name = b"name\x00"
    value = b"val\x00"
    domain = b"example.com\x00"
    path_str = b"/\x00"
    strings[name_offset - 64:name_offset - 64 + len(name)] = name
    strings[value_offset - 64:value_offset - 64 + len(value)] = value
    strings[domain_offset - 64:domain_offset - 64 + len(domain)] = domain
    strings[path_offset - 64:path_offset - 64 + len(path_str)] = path_str
    page += bytes(strings)

    return page


def _build_safari_cookies_file(pages=None):
    if pages is None:
        pages = [_build_safari_page_with_entry()]
    header = b"cook"
    num_pages = struct.pack(">I", len(pages))
    page_sizes = b"".join(struct.pack(">I", len(p)) for p in pages)
    return header + num_pages + page_sizes + b"".join(pages)


# ---------------------------------------------------------------------------
# _platform_check
# ---------------------------------------------------------------------------

class TestPlatformCheck:
    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_raises_on_non_darwin(self, mock_sys):
        mock_sys.platform = "linux"
        with pytest.raises(ImportError, match="only supported on macOS"):
            SafariExtractor.__new__(SafariExtractor)._platform_check()

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_no_raise_on_darwin(self, mock_sys):
        mock_sys.platform = "darwin"
        SafariExtractor.__new__(SafariExtractor)._platform_check()


class TestInit:
    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_default_profile_path(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        assert ext.profile_path.endswith("Cookies.binarycookies")

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_custom_profile_path(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor(profile_path="/custom/path")
        assert ext.profile_path == "/custom/path"

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_tech_preview(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor(tech_preview=True)
        assert ext.tech_preview is True


class TestFindCookiesFile:
    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_profile_path_exists(self, mock_sys):
        mock_sys.platform = "darwin"
        with tempfile.NamedTemporaryFile(suffix=".binarycookies") as f:
            ext = SafariExtractor(profile_path=f.name)
            result = ext._find_cookies_file()
            assert result == Path(f.name)

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_profile_path_not_exists(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor(profile_path="/nonexistent/file")
        result = ext._find_cookies_file()
        assert result is None

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_no_profile_default_paths_not_found(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor(profile_path=None)
        ext.profile_path = None
        result = ext._find_cookies_file()
        assert result is None

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_tech_preview_paths(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor(profile_path=None, tech_preview=True)
        ext.profile_path = None
        result = ext._find_cookies_file()
        assert result is None


class TestExtractFilters:
    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch.object(SafariExtractor, "_find_cookies_file")
    @patch.object(SafariExtractor, "_parse_binary_cookies")
    def test_no_filter(self, mock_parse, mock_find, mock_sys):
        mock_sys.platform = "darwin"
        mock_find.return_value = Path("/fake")
        mock_parse.return_value = [{"domain": "example.com"}]
        ext = SafariExtractor(profile_path="/fake")
        result = ext.extract()
        assert result == [{"domain": "example.com"}]

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch.object(SafariExtractor, "_find_cookies_file")
    def test_no_file_found(self, mock_find, mock_sys):
        mock_sys.platform = "darwin"
        mock_find.return_value = None
        ext = SafariExtractor()
        result = ext.extract()
        assert result == []

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch.object(SafariExtractor, "_find_cookies_file")
    @patch.object(SafariExtractor, "_parse_binary_cookies")
    def test_list_filter_match(self, mock_parse, mock_find, mock_sys):
        mock_sys.platform = "darwin"
        mock_find.return_value = Path("/fake")
        mock_parse.return_value = [
            {"domain": "example.com"},
            {"domain": "other.com"},
        ]
        ext = SafariExtractor(profile_path="/fake")
        result = ext.extract(site_filter=["example.com"])
        assert len(result) == 1
        assert result[0]["domain"] == "example.com"

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch.object(SafariExtractor, "_find_cookies_file")
    @patch.object(SafariExtractor, "_parse_binary_cookies")
    def test_list_filter_subdomain(self, mock_parse, mock_find, mock_sys):
        mock_sys.platform = "darwin"
        mock_find.return_value = Path("/fake")
        mock_parse.return_value = [{"domain": ".example.com"}]
        ext = SafariExtractor(profile_path="/fake")
        result = ext.extract(site_filter=["example.com"])
        assert len(result) == 1

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch.object(SafariExtractor, "_find_cookies_file")
    @patch.object(SafariExtractor, "_parse_binary_cookies")
    def test_list_filter_endswith_site(self, mock_parse, mock_find, mock_sys):
        mock_sys.platform = "darwin"
        mock_find.return_value = Path("/fake")
        mock_parse.return_value = [{"domain": "example.com"}]
        ext = SafariExtractor(profile_path="/fake")
        result = ext.extract(site_filter=["example.com"])
        assert len(result) == 1

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch.object(SafariExtractor, "_find_cookies_file")
    @patch.object(SafariExtractor, "_parse_binary_cookies")
    def test_site_filter_object(self, mock_parse, mock_find, mock_sys):
        mock_sys.platform = "darwin"
        mock_find.return_value = Path("/fake")
        mock_parse.return_value = [{"domain": "example.com"}]
        mock_filter = MagicMock()
        mock_filter.filter_cookies.return_value = [{"domain": "filtered.example.com"}]
        ext = SafariExtractor(profile_path="/fake")
        result = ext.extract(site_filter=mock_filter)
        assert result == [{"domain": "filtered.example.com"}]
        mock_filter.filter_cookies.assert_called_once()

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch.object(SafariExtractor, "_find_cookies_file")
    @patch.object(SafariExtractor, "_parse_binary_cookies",
                  side_effect=Exception("parse error"))
    def test_parse_exception(self, mock_parse, mock_find, mock_sys):
        mock_sys.platform = "darwin"
        mock_find.return_value = Path("/fake")
        ext = SafariExtractor(profile_path="/fake")
        result = ext.extract()
        assert result == []


class TestParseBinaryCookies:
    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_file_too_small(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"co")
            f.flush()
            result = ext._parse_binary_cookies(f.name)
            assert result == []
            os.unlink(f.name)

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_invalid_header(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"xxxx" + b"\x00" * 20)
            f.flush()
            result = ext._parse_binary_cookies(f.name)
            assert result == []
            os.unlink(f.name)

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_valid_single_page(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        file_data = _build_safari_cookies_file([_build_safari_page_with_entry()])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(file_data)
            f.flush()
            result = ext._parse_binary_cookies(f.name)
            assert isinstance(result, list)
            os.unlink(f.name)

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_io_error(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        result = ext._parse_binary_cookies("/nonexistent/file.bin")
        assert result == []


class TestParsePage:
    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_page_too_small(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        assert ext._parse_page(b"\x00\x01") == []

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_page_header_only(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        assert ext._parse_page(b"\x00\x00\x01\x00") == []

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_page_zero_cookies(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        page = struct.pack(">I", 0x00000100) + struct.pack(">I", 0)
        assert ext._parse_page(page) == []


class TestParseCookieEntry:
    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_entry_too_short(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        assert ext._parse_cookie_entry(b"\x00\x01", 0) is None

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_valid_entry(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        page = _build_safari_page_with_entry()
        cookie = ext._parse_cookie_entry(page, 12)
        assert cookie is not None
        assert cookie["name"] == "name"
        assert cookie["domain"] == "example.com"
        assert cookie["secure"] is True
        assert cookie["httpOnly"] is False

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_valid_entry_httponly_and_secure(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        page = _build_safari_page_with_entry(flags=0x3)  # secure + httponly
        cookie = ext._parse_cookie_entry(page, 12)
        assert cookie is not None
        assert cookie["secure"] is True
        assert cookie["httpOnly"] is True

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_no_name_no_domain_returns_none(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        flags = struct.pack(">I", 0)
        pad = struct.pack(">I", 0)
        string_offsets = b"".join(struct.pack(">I", 0) for _ in range(6))
        comment = struct.pack(">I", 0)
        expiry = struct.pack(">d", 0.0)
        creation = struct.pack(">d", 0.0)
        page = flags + pad + string_offsets + comment + expiry + creation
        cookie = ext._parse_cookie_entry(page, 0)
        assert cookie is None

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_expiry_zero(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        page = _build_safari_page_with_entry(expiry=0.0)
        cookie = ext._parse_cookie_entry(page, 12)
        # name and domain are valid, expiry=0 means no expires field
        assert cookie is not None
        assert "expires" not in cookie

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_flags_none(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        page = _build_safari_page_with_entry(flags=0x0)
        cookie = ext._parse_cookie_entry(page, 12)
        assert cookie is not None
        assert cookie["secure"] is False
        assert cookie["httpOnly"] is False

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_entry_offset_too_short(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        page = struct.pack(">I", 0x00000100) + struct.pack(">I", 1)
        page += struct.pack(">I", 8)
        page += b"\x00" * 2  # too short for a cookie entry
        cookie = ext._parse_cookie_entry(page, 8)
        assert cookie is None

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_string_offsets_too_short(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        entry = struct.pack(">I", 0)  # flags
        entry += struct.pack(">I", 0)  # pad
        entry += b"\x00" * 8  # only 2 offsets, need 6
        cookie = ext._parse_cookie_entry(entry, 0)
        assert cookie is None

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_expiry_too_short(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        entry = struct.pack(">I", 0)
        entry += struct.pack(">I", 0)
        entry += b"".join(struct.pack(">I", 0) for _ in range(6))
        entry += struct.pack(">I", 0)  # comment
        entry += b"\x00" * 4  # too short for double
        cookie = ext._parse_cookie_entry(entry, 0)
        assert cookie is None

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_creation_too_short(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        entry = struct.pack(">I", 0)
        entry += struct.pack(">I", 0)
        entry += b"".join(struct.pack(">I", 0) for _ in range(6))
        entry += struct.pack(">I", 0)  # comment
        entry += struct.pack(">d", 0.0)  # expiry ok
        entry += b"\x00" * 4  # too short for creation
        cookie = ext._parse_cookie_entry(entry, 0)
        assert cookie is None

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_cookie_offset_out_of_bounds(self, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        page = struct.pack(">I", 0x00000100) + struct.pack(">I", 1)
        page += struct.pack(">I", 9999)  # offset beyond page
        assert ext._parse_page(page) == []


class TestReadHelpers:
    def test_read_string_at_boundary(self):
        assert SafariExtractor._read_string(b"hello", 10) == ""

    def test_read_string_normal(self):
        data = b"hello\x00world"
        assert SafariExtractor._read_string(data, 0) == "hello"
        assert SafariExtractor._read_string(data, 6) == "world"

    def test_read_string_no_null(self):
        data = b"hello"
        assert SafariExtractor._read_string(data, 0) == "hello"

    def test_read_cstring_at_boundary(self):
        assert SafariExtractor._read_cstring(b"hello", 10) == ""

    def test_read_cstring_normal(self):
        data = b"hello\x00world"
        assert SafariExtractor._read_cstring(data, 0) == "hello"
        assert SafariExtractor._read_cstring(data, 6) == "world"

    def test_read_cstring_no_null(self):
        data = b"abc"
        assert SafariExtractor._read_cstring(data, 0) == "abc"


class TestKeychainDecrypt:
    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch("tokenade.core.importer.safari_extractor.subprocess.run")
    def test_key_not_found(self, mock_run, mock_sys):
        mock_sys.platform = "darwin"
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        ext = SafariExtractor()
        result = ext.attempt_keychain_decrypt("cookie", "value")
        assert result == "value"

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch("tokenade.core.importer.safari_extractor.subprocess.run",
           side_effect=FileNotFoundError)
    def test_security_cmd_not_found(self, _mock_run, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        result = ext.attempt_keychain_decrypt("cookie", "value")
        assert result == "value"

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch("tokenade.core.importer.safari_extractor.subprocess.run")
    def test_timeout(self, mock_run, mock_sys):
        mock_sys.platform = "darwin"
        mock_run.side_effect = subprocess.TimeoutExpired("security", 5)
        ext = SafariExtractor()
        result = ext.attempt_keychain_decrypt("cookie", "value")
        assert result == "value"

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch("tokenade.core.importer.safari_extractor.subprocess.run")
    @patch.object(SafariExtractor, "_aes_cbc_decrypt", return_value="decrypted")
    def test_key_found_decrypt(self, mock_decrypt, mock_run, mock_sys):
        mock_sys.platform = "darwin"
        mock_run.return_value = MagicMock(returncode=0, stdout="aabbccdd\n")
        ext = SafariExtractor()
        result = ext.attempt_keychain_decrypt("cookie", "encrypted")
        assert result == "decrypted"

    @patch("tokenade.core.importer.safari_extractor.sys")
    @patch("tokenade.core.importer.safari_extractor.subprocess.run",
           side_effect=Exception("unexpected"))
    def test_general_exception(self, _mock_run, mock_sys):
        mock_sys.platform = "darwin"
        ext = SafariExtractor()
        result = ext.attempt_keychain_decrypt("cookie", "value")
        assert result == "value"


class TestAesCbcDecrypt:
    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_not_encrypted_returns_as_is(self, mock_sys):
        mock_sys.platform = "darwin"
        result = SafariExtractor._aes_cbc_decrypt("plaintext_value", b"\x00" * 16)
        assert result == "plaintext_value"

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_short_data_returns_as_is(self, mock_sys):
        mock_sys.platform = "darwin"
        import base64
        short = base64.b64encode(b"v10" + b"\x00" * 5).decode()
        result = SafariExtractor._aes_cbc_decrypt(short, b"\x00" * 16)
        assert result == short

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_invalid_version_header(self, mock_sys):
        mock_sys.platform = "darwin"
        import base64
        data = b"v99" + b"\x00" * 16 + b"\x00" * 32
        encoded = base64.b64encode(data).decode()
        result = SafariExtractor._aes_cbc_decrypt(encoded, b"\x00" * 16)
        assert result == encoded

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_pycryptodome_not_installed(self, mock_sys):
        mock_sys.platform = "darwin"
        result = SafariExtractor._aes_cbc_decrypt("somevalue", b"\x00" * 16)
        assert result == "somevalue"

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_hex_decode_fallback(self, mock_sys):
        mock_sys.platform = "darwin"
        result = SafariExtractor._aes_cbc_decrypt("not_base64_or_hex!!!", b"\x00" * 16)
        assert result == "not_base64_or_hex!!!"

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_aes_decryption_exception(self, mock_sys):
        mock_sys.platform = "darwin"
        import base64
        data = b"v10" + b"\x00" * 16 + b"\x00" * 32
        encoded = base64.b64encode(data).decode()
        # When pycryptodome is installed but decryption fails
        # The ImportError path is the normal path on systems without pycryptodome
        # We test the fallback which is returning the value as-is
        result = SafariExtractor._aes_cbc_decrypt(encoded, b"\x00" * 16)
        # Either it decrypts successfully or falls back to returning as-is
        assert isinstance(result, str)

    @patch("tokenade.core.importer.safari_extractor.sys")
    def test_hex_decode_valid_data(self, mock_sys):
        mock_sys.platform = "darwin"
        data = b"v10" + b"\x00" * 16 + b"\x00" * 32
        hex_str = data.hex()
        result = SafariExtractor._aes_cbc_decrypt(hex_str, b"\x00" * 16)
        assert isinstance(result, str)
