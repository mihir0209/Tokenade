"""
Tests for advanced engineering additions:
1. IndexedDB State Portability in SessionPackager & SessionLoader
2. SecureBuffer and memory zeroization
3. Advanced Audio/WebRTC stealth patches
4. Google & GitHub OAuth automation handlers
5. S3 transport in TUI sync view
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tokenade.core.browser.stealth.manager import StealthConfig, build_stealth_script
from tokenade.core.crypto.secure_memory import SecureBuffer, zero_memory
from tokenade.core.importer.session_loader import SessionLoader
from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.integration.oauth_handlers import GitHubOAuthAutomation, GoogleOAuthAutomation


class TestIndexedDBPortability:
    """Tests for IndexedDB packaging and injection support."""

    def test_session_packager_with_indexeddb(self):
        packager = SessionPackager()
        cookies = [{"name": "sid", "value": "123", "domain": "example.com"}]
        idb_sample = {
            "auth_db": {
                "version": 1,
                "stores": {
                    "tokens": {"access_token": "secret_abc"}
                }
            }
        }
        pkg = packager.package(cookies=cookies, indexeddb=idb_sample)
        assert "storage" in pkg
        assert "indexeddb" in pkg["storage"]
        assert "https://example.com" in pkg["storage"]["indexeddb"]
        assert pkg["storage"]["indexeddb"]["https://example.com"]["auth_db"]["version"] == 1

    def test_session_loader_indexeddb_injection(self):
        loader = SessionLoader()
        mock_bm = MagicMock()
        mock_bm.evaluate_with_arg.return_value = 1

        idb_sample = {
            "app_db": {"version": 1, "stores": {"users": {"u1": "data"}}}
        }
        injected = loader.inject_indexeddb(mock_bm, idb_sample)
        assert injected == 1
        mock_bm.evaluate_with_arg.assert_called_once()


class TestSecureMemoryZeroization:
    """Tests for in-memory zeroization and SecureBuffer."""

    def test_zero_memory_bytearray(self):
        buf = bytearray(b"super_sensitive_encryption_key_1234")
        zero_memory(buf)
        assert buf == bytearray(len(buf))

    def test_secure_buffer_context_manager(self):
        with SecureBuffer(b"my_temp_secret") as sbuf:
            assert sbuf.raw_bytes == b"my_temp_secret"
            internal_buf = sbuf.buffer

        # After exiting context, buffer is zeroized
        assert internal_buf == bytearray(len(b"my_temp_secret"))
        with pytest.raises(ValueError, match="already been zeroized"):
            _ = sbuf.raw_bytes


class TestStealthEnhancements:
    """Tests for Audio and WebRTC stealth patches."""

    def test_stealth_script_contains_audio_and_webrtc(self):
        cfg = StealthConfig(enable_audio_spoofing=True, enable_webrtc_protection=True)
        script = build_stealth_script(cfg)
        assert "AudioContext" in script
        assert "RTCPeerConnection" in script
        assert "getFloatFrequencyData" in script


class TestOAuthAutomationHandlers:
    """Tests for Google and GitHub OAuth automated login flows."""

    def test_oauth_handler_instantiation(self):
        google_auth = GoogleOAuthAutomation()
        assert "Sign in with Google" in google_auth.oauth_button_selector

        github_auth = GitHubOAuthAutomation()
        assert "Sign in with GitHub" in github_auth.oauth_button_selector
