"""Tests for Phase 80 — Integration, StorageExtractor, Plugin Export."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.browser.storage_extractor import StorageExtractor
from tokenade.core.importer.plugin_export import PluginExporter
from tokenade.cli.session_export import _site_handler_metadata


# ─── StorageExtractor Tests ────────────────────────────────

class TestStorageExtractor:
    def test_init(self):
        ext = StorageExtractor()
        assert ext is not None

    @pytest.mark.asyncio
    async def test_extract_all_returns_structure(self):
        ext = StorageExtractor()
        mock_cdp = MagicMock()
        async def mock_send(*args, **kwargs):
            return {"result": {"type": "string", "value": "{}"}}
        mock_cdp.send = mock_send
        result = await ext.extract_all(mock_cdp)
        assert "local" in result
        assert "session" in result
        assert isinstance(result["local"], dict)
        assert isinstance(result["session"], dict)

    @pytest.mark.asyncio
    async def test_inject_local_storage(self):
        ext = StorageExtractor()
        mock_cdp = MagicMock()
        # send must be async
        async def mock_send(*args, **kwargs):
            return {"result": {"type": "undefined"}}
        mock_cdp.send = mock_send
        count = await ext.inject_local_storage(mock_cdp, {"https://test.com": {"k": "v"}})
        assert count == 1

    @pytest.mark.asyncio
    async def test_inject_session_storage(self):
        ext = StorageExtractor()
        mock_cdp = MagicMock()
        async def mock_send(*args, **kwargs):
            return {"result": {"type": "undefined"}}
        mock_cdp.send = mock_send
        count = await ext.inject_session_storage(mock_cdp, {"https://test.com": {"k": "v"}})
        assert count == 1

    @pytest.mark.asyncio
    async def test_inject_empty_storage(self):
        ext = StorageExtractor()
        mock_cdp = MagicMock()
        async def mock_send(*args, **kwargs):
            return {"result": {"type": "undefined"}}
        mock_cdp.send = mock_send
        count = await ext.inject_local_storage(mock_cdp, {})
        assert count == 0


# ─── PluginExporter Tests ──────────────────────────────────

class TestPluginExporter:
    def test_init(self):
        exporter = PluginExporter()
        assert exporter._handlers == {}

    def test_list_handlers_returns_list(self):
        exporter = PluginExporter()
        handlers = exporter.list_handlers()
        assert isinstance(handlers, list)

    def test_find_handler_returns_none_when_empty(self):
        exporter = PluginExporter()
        exporter._handlers = {}
        exporter._load_handlers = lambda: None  # Prevent loading
        handler = exporter.find_handler(["example.com"])
        assert handler is None

    def test_find_handler_with_handler(self):
        exporter = PluginExporter()
        mock_handler = MagicMock()
        mock_handler.can_handle = MagicMock(return_value=True)
        mock_handler.name = "google-handler"
        exporter._handlers = {"google-handler": mock_handler}
        handler = exporter.find_handler(["google.com"])
        assert handler is not None

    def test_find_handler_no_match(self):
        exporter = PluginExporter()
        mock_handler = MagicMock()
        mock_handler.can_handle = MagicMock(return_value=False)
        exporter._handlers = {"google-handler": mock_handler}
        handler = exporter.find_handler(["example.com"])
        assert handler is None

    def test_find_handler_prefers_specific_over_generic(self):
        """Specific handler wins over generic-handler when both can_handle the domain."""
        exporter = PluginExporter()
        specific = MagicMock()
        specific.can_handle = MagicMock(return_value=True)
        specific.name = "google-handler"
        generic = MagicMock()
        generic.can_handle = MagicMock(return_value=True)
        generic.name = "generic-handler"
        exporter._handlers = {"google-handler": specific, "generic-handler": generic}
        exporter._load_handlers = lambda: None
        handler = exporter.find_handler(["google.com"])
        assert handler is specific

    def test_find_handler_generic_fallback_when_no_specific(self):
        """Generic handler used when no specific handler matches."""
        exporter = PluginExporter()
        generic = MagicMock()
        generic.can_handle = MagicMock(return_value=True)
        generic.name = "generic-handler"
        exporter._handlers = {"generic-handler": generic}
        exporter._load_handlers = lambda: None
        handler = exporter.find_handler(["unknown.com"])
        assert handler is generic

    def test_find_handler_specific_name_tiebreak(self):
        """When two specific handlers match, the one whose name appears in domains wins."""
        exporter = PluginExporter()
        google = MagicMock()
        google.can_handle = MagicMock(return_value=True)
        google.name = "google-handler"
        github = MagicMock()
        github.can_handle = MagicMock(return_value=True)
        github.name = "github-handler"
        exporter._handlers = {"google-handler": google, "github-handler": github}
        exporter._load_handlers = lambda: None
        handler = exporter.find_handler(["google.com", "mail.google.com"])
        assert handler is google

    def test_site_handler_metadata_includes_lineage(self):
        handler = MagicMock()
        handler.name = "discord-handler"
        handler.version = "1.2.0"
        handler.get_export_domains.return_value = ["discord.com", "discordapp.com"]
        handler.get_storage_origins.return_value = ["https://discord.com"]

        metadata = _site_handler_metadata(handler, explicit_plugin="discord-handler")

        assert metadata["plugin_name"] == "discord-handler"
        assert metadata["plugin_version"] == "1.2.0"
        assert metadata["handler_name"] == "discord-handler"
        assert metadata["export_domains"] == ["discord.com", "discordapp.com"]
        assert metadata["storage_origins"] == ["https://discord.com"]
        assert metadata["auto_discovered"] is False


# ─── v3.0 Format Tests ────────────────────────────────────

class TestV3Format:
    def test_v3_package_with_storage(self, tmp_path):
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        cookies = [{"name": "c1", "value": "v1", "domain": ".example.com"}]
        storage = {
            "local": {"https://example.com": {"key1": "val1"}},
            "session": {"https://example.com": {"skey": "sval"}},
        }
        pkg = packager.package(cookies=cookies, storage=storage)
        assert pkg["version"] == "3.1"
        assert pkg["storage"]["local"]["https://example.com"]["key1"] == "val1"
        assert pkg["storage"]["session"]["https://example.com"]["skey"] == "sval"
        assert pkg["metadata"]["local_storage_count"] == 1
        assert pkg["metadata"]["session_storage_count"] == 1

    def test_v3_backward_compat_flat_local_storage(self, tmp_path):
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        cookies = [{"name": "c1", "value": "v1", "domain": ".example.com"}]
        local = {"key1": "val1"}
        pkg = packager.package(cookies=cookies, local_storage=local)
        assert pkg["version"] == "3.1"
        assert pkg["storage"]["local"]["https://example.com"]["key1"] == "val1"

    def test_v3_save_load_roundtrip(self, tmp_path):
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        cookies = [{"name": "c1", "value": "v1", "domain": ".example.com"}]
        storage = {
            "local": {"https://example.com": {"k": "v"}},
            "session": {},
        }
        pkg = packager.package(cookies=cookies, storage=storage)
        path = str(tmp_path / "test.tokenade")
        packager.save(pkg, path)

        with open(path) as f:
            loaded = json.load(f)

        assert loaded["version"] == "3.1"
        assert loaded["storage"]["local"]["https://example.com"]["k"] == "v"
        assert len(loaded["cookies"]) == 1


# ─── Session State v3.0 Tests ─────────────────────────────

class TestSessionStateV3:
    def test_v3_to_storage_state(self, tmp_path):
        from tokenade.core.browser.session_state import tokenade_to_storage_state
        session = {
            "version": "3.0",
            "cookies": [
                {"name": "c1", "value": "v1", "domain": ".example.com",
                 "path": "/", "secure": True, "httpOnly": False,
                 "sameSite": "Lax", "expires": 1700000000},
            ],
            "storage": {
                "local": {"https://example.com": {"key1": "val1"}},
                "session": {},
            },
        }
        path = tmp_path / "test.tokenade"
        path.write_text(json.dumps(session))

        state = tokenade_to_storage_state(str(path))
        assert len(state["cookies"]) == 1
        assert len(state["origins"]) == 1
        assert state["origins"][0]["localStorage"][0]["name"] == "key1"

    def test_v2_to_storage_state_compat(self, tmp_path):
        from tokenade.core.browser.session_state import tokenade_to_storage_state
        session = {
            "version": "2.0",
            "cookies": [
                {"name": "c1", "value": "v1", "domain": ".example.com",
                 "path": "/", "secure": True, "httpOnly": False,
                 "sameSite": "Lax", "expires": 1700000000},
            ],
            "local_storage": {"key1": "val1"},
        }
        path = tmp_path / "test.tokenade"
        path.write_text(json.dumps(session))

        state = tokenade_to_storage_state(str(path))
        assert len(state["cookies"]) == 1
        assert len(state["origins"]) == 1


# ─── Encryption Tests ─────────────────────────────────────

class TestEncryptionExport:
    def test_encrypt_decrypt_roundtrip(self, tmp_path):
        from tokenade.core.crypto.encryptor import TokenadeEncryptor
        encryptor = TokenadeEncryptor()

        # Create test data
        data = {"version": "3.0", "cookies": [{"name": "c1", "value": "v1"}]}
        input_path = str(tmp_path / "test.tokenade")
        enc_path = str(tmp_path / "test.tokenade.enc")
        dec_path = str(tmp_path / "test.tokenade.dec")

        with open(input_path, 'w') as f:
            json.dump(data, f)

        # Encrypt
        encryptor.encrypt_file(input_path, enc_path, "testpass123")
        assert os.path.exists(enc_path)

        # Decrypt
        encryptor.decrypt_file(enc_path, dec_path, "testpass123")
        assert os.path.exists(dec_path)

        # Verify
        with open(dec_path) as f:
            loaded = json.load(f)
        assert loaded["cookies"][0]["name"] == "c1"


# ─── CLI Parser Tests ─────────────────────────────────────

class TestPhase80CLIParsers:
    def test_export_full_flag(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["export", "--browser-name", "brave", "--full"])
        assert a.full is True

    def test_export_encrypt_password(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["export", "--browser-name", "brave", "--encrypt-password", "secret"])
        assert a.encrypt_password == "secret"

    def test_export_no_plugin(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["export", "--browser-name", "brave", "--no-plugin"])
        assert a.no_plugin is True

    def test_export_plugin(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["export", "--browser-name", "brave", "--plugin", "google-handler"])
        assert a.plugin == "google-handler"

    def test_export_list_handlers(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["export", "--browser-name", "brave", "--list-handlers"])
        assert a.list_handlers is True

    def test_launch_decrypt_password(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["launch", "-s", "test.tokenade", "--decrypt-password", "secret"])
        assert a.decrypt_password == "secret"

    def test_proxy_decrypt_password(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["proxy", "-s", "test.tokenade", "--decrypt-password", "secret"])
        assert a.decrypt_password == "secret"
