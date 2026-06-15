"""Tests for session sharer."""

import hashlib
import hmac
import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
from tokenade.core.importer.session_sharer import (
    SessionSharer,
    ShareConfig,
    SharedSession,
    SessionVersion,
    generate_share_html,
)


class TestShareConfig:
    def test_default_config(self):
        config = ShareConfig()
        assert config.expiry_hours == 24
        assert config.max_uses == 0
        assert config.password_protected is False
        assert config.password is None
        assert config.email_recipients == []
        assert config.smtp_host is None
        assert config.webhook_url is None

    def test_custom_config(self):
        config = ShareConfig(
            expiry_hours=48,
            max_uses=10,
            password_protected=True,
            password="secret",
            email_recipients=["user@example.com"],
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            webhook_url="https://example.com/hook",
        )
        assert config.expiry_hours == 48
        assert config.max_uses == 10
        assert config.password_protected is True
        assert config.password == "secret"
        assert config.email_recipients == ["user@example.com"]
        assert config.smtp_host == "smtp.gmail.com"
        assert config.webhook_url == "https://example.com/hook"


class TestSessionSharer:
    @pytest.fixture
    def session(self):
        return {
            "version": "2.0",
            "site_name": "test_site",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
            ],
        }

    @pytest.fixture
    def sharer(self, tmp_path):
        return SessionSharer(storage_dir=str(tmp_path / "shared"))

    def test_create_share_link(self, sharer, session):
        url, session_id = sharer.create_share_link(session)
        assert url.startswith("tokenade://share/")
        assert len(session_id) > 0

    def test_create_share_link_with_expiry(self, sharer, session):
        config = ShareConfig(expiry_hours=48)
        url, session_id = sharer.create_share_link(session, config)
        assert url.startswith("tokenade://share/")

    def test_create_share_link_with_password(self, sharer, session):
        config = ShareConfig(password_protected=True, password="secret")
        url, session_id = sharer.create_share_link(session, config)
        assert url.startswith("tokenade://share/")

    def test_load_from_url(self, sharer, session):
        url, session_id = sharer.create_share_link(session)
        loaded = sharer.load_from_url(url)
        assert loaded is not None
        assert loaded["site_name"] == session["site_name"]
        assert len(loaded["cookies"]) == len(session["cookies"])

    def test_load_from_url_with_password(self, sharer, session):
        config = ShareConfig(password_protected=True, password="secret")
        url, session_id = sharer.create_share_link(session, config)
        loaded = sharer.load_from_url(url, password="secret")
        assert loaded is not None

    def test_load_from_url_with_password_in_url(self, sharer, session):
        # Password-protected URL requires the password to decrypt
        config = ShareConfig(password_protected=True, password="secret")
        url, session_id = sharer.create_share_link(session, config)
        # Load with correct password
        loaded = sharer.load_from_url(url, password="secret")
        assert loaded is not None
        # Load without password fails (password is NOT embedded in URL)
        loaded_no_pw = sharer.load_from_url(url)
        assert loaded_no_pw is None

    def test_list_shared(self, sharer, session):
        sharer.create_share_link(session)
        sharer.create_share_link(session)
        shared_list = sharer.list_shared()
        assert len(shared_list) == 2

    def test_revoke_share(self, sharer, session):
        _, session_id = sharer.create_share_link(session)
        assert sharer.revoke_share(session_id) is True
        shared_list = sharer.list_shared()
        assert len(shared_list) == 0

    def test_load_shared_expired(self, sharer, session):
        config = ShareConfig(expiry_hours=0)  # Expire immediately
        _, session_id = sharer.create_share_link(session, config)
        time.sleep(0.1)
        loaded = sharer.load_shared(session_id)
        assert loaded is None

    def test_load_shared_max_uses(self, sharer, session):
        config = ShareConfig(max_uses=2)
        _, session_id = sharer.create_share_link(session, config)
        
        # First use
        loaded = sharer.load_shared(session_id)
        assert loaded is not None
        
        # Second use
        loaded = sharer.load_shared(session_id)
        assert loaded is not None
        
        # Third use should fail
        loaded = sharer.load_shared(session_id)
        assert loaded is None

    def test_generate_share_html(self, sharer, session, tmp_path):
        output_path = str(tmp_path / "share.html")
        result = generate_share_html(session, output_path)
        assert result == output_path
        assert Path(output_path).exists()
        
        content = Path(output_path).read_text()
        assert "Tokenade Shared Session" in content
        assert session["site_name"] in content

    def test_send_email_no_config(self, sharer, session):
        config = ShareConfig()
        success, msg = sharer.send_email(session, config)
        assert success is False
        assert "SMTP host not configured" in msg

    def test_send_email_no_recipients(self, sharer, session):
        config = ShareConfig(smtp_host="smtp.gmail.com")
        success, msg = sharer.send_email(session, config)
        assert success is False
        assert "No email recipients" in msg

    def test_send_webhook_no_config(self, sharer, session):
        config = ShareConfig()
        success, msg = sharer.send_webhook(session, config)
        assert success is False
        assert "Webhook URL not configured" in msg

    def test_send_webhook_invalid_url(self, sharer, session):
        config = ShareConfig(webhook_url="ftp://invalid.com")
        success, msg = sharer.send_webhook(session, config)
        assert success is False
        assert "Invalid webhook URL scheme" in msg

    def test_create_version(self, sharer, session):
        version_id = sharer.create_version(session, changes="Initial version")
        assert version_id is not None
        assert "test_site" in version_id

    def test_list_versions(self, sharer, session):
        sharer.create_version(session, changes="Version 1")
        sharer.create_version(session, changes="Version 2")
        versions = sharer.list_versions()
        assert len(versions) == 2
        # Should be sorted by created_at descending
        assert versions[0]["changes"] == "Version 2"

    def test_list_versions_filtered(self, sharer, session):
        sharer.create_version(session, changes="Version 1")
        other_session = {"site_name": "other_site", "cookies": []}
        sharer.create_version(other_session, changes="Other")
        
        versions = sharer.list_versions(site_name="test_site")
        assert len(versions) == 1

    def test_load_version(self, sharer, session):
        version_id = sharer.create_version(session, changes="Test")
        loaded = sharer.load_version(version_id)
        assert loaded is not None
        assert loaded["site_name"] == session["site_name"]

    def test_load_version_not_found(self, sharer):
        loaded = sharer.load_version("nonexistent_version")
        assert loaded is None

    def test_rollback_version(self, sharer, session):
        version_id = sharer.create_version(session, changes="Rollback target")
        rolled_back = sharer.rollback_version(version_id)
        assert rolled_back is not None
        assert rolled_back["site_name"] == session["site_name"]

    def test_rollback_version_not_found(self, sharer):
        result = sharer.rollback_version("nonexistent")
        assert result is None


class TestSharedSession:
    def test_shared_session_dataclass(self):
        shared = SharedSession(
            session_id="test123",
            created_at=time.time(),
            expires_at=time.time() + 86400,
            max_uses=0,
            use_count=0,
            password_hash=None,
            session_data={"site_name": "test"},
        )
        assert shared.session_id == "test123"
        assert shared.max_uses == 0
        assert shared.use_count == 0


class TestSessionVersion:
    def test_version_dataclass(self):
        version = SessionVersion(
            version_id="test_v1",
            created_at=time.time(),
            cookies_count=5,
            changes="Added new cookies",
            session_data={"site_name": "test"},
        )
        assert version.version_id == "test_v1"
        assert version.cookies_count == 5
        assert version.changes == "Added new cookies"


class TestSessionSharerEmail:
    @pytest.fixture
    def session(self):
        return {
            "version": "2.0",
            "site_name": "gmail",
            "cookies": [
                {"name": "SID", "value": "abc", "domain": ".google.com", "path": "/"},
                {"name": "HSID", "value": "def", "domain": ".google.com", "path": "/"},
            ],
        }

    @pytest.fixture
    def sharer(self, tmp_path):
        return SessionSharer(storage_dir=str(tmp_path / "shared"))

    def test_send_email_success(self, sharer, session):
        config = ShareConfig(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_user="sender@gmail.com",
            smtp_password="app_password",
            email_recipients=["recipient@example.com"],
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            success, msg = sharer.send_email(session, config)
            assert success is True
            assert "1 recipients" in msg

            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("sender@gmail.com", "app_password")
            mock_server.sendmail.assert_called_once()

    def test_send_email_custom_subject(self, sharer, session):
        config = ShareConfig(
            smtp_host="smtp.gmail.com",
            smtp_user="sender@gmail.com",
            email_recipients=["r@example.com"],
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            success, msg = sharer.send_email(session, config, subject="Custom Subject")
            assert success is True

            call_args = mock_server.sendmail.call_args
            email_body = call_args[0][2]
            assert "Custom Subject" in email_body

    def test_send_email_smtp_error(self, sharer, session):
        import smtplib

        config = ShareConfig(
            smtp_host="smtp.gmail.com",
            smtp_user="sender@gmail.com",
            email_recipients=["r@example.com"],
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__ = MagicMock(side_effect=smtplib.SMTPException("Connection refused"))
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            success, msg = sharer.send_email(session, config)
            assert success is False
            assert "Connection refused" in msg

    def test_send_email_no_auth(self, sharer, session):
        config = ShareConfig(
            smtp_host="smtp.gmail.com",
            email_recipients=["r@example.com"],
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            success, msg = sharer.send_email(session, config)
            assert success is True
            mock_server.login.assert_not_called()

    def test_send_email_custom_from(self, sharer, session):
        config = ShareConfig(
            smtp_host="smtp.gmail.com",
            smtp_user="sender@gmail.com",
            smtp_from="custom@domain.com",
            email_recipients=["r@example.com"],
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            success, msg = sharer.send_email(session, config)
            assert success is True

            call_args = mock_server.sendmail.call_args
            assert call_args[0][0] == "custom@domain.com"


class TestSessionSharerWebhook:
    @pytest.fixture
    def session(self):
        return {
            "version": "2.0",
            "site_name": "reddit",
            "cookies": [
                {"name": "reddit_session", "value": "xyz", "domain": ".reddit.com", "path": "/"},
            ],
        }

    @pytest.fixture
    def sharer(self, tmp_path):
        return SessionSharer(storage_dir=str(tmp_path / "shared"))

    def test_send_webhook_success(self, sharer, session):
        config = ShareConfig(webhook_url="https://hooks.example.com/session")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 200
            mock_resp.read.return_value = b'{"ok": true}'
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            success, msg = sharer.send_webhook(session, config)
            assert success is True
            assert "HTTP 200" in msg

    def test_send_webhook_with_secret(self, sharer, session):
        config = ShareConfig(
            webhook_url="https://hooks.example.com/session",
            webhook_secret="my_secret_key",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 200
            mock_resp.read.return_value = b'ok'
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            success, msg = sharer.send_webhook(session, config)
            assert success is True

            req = mock_urlopen.call_args[0][0]
            # urllib.request.Request lowercases header names
            assert "x-tokenade-signature" in {k.lower() for k in req.headers}
            sig = req.headers.get("X-tokenade-signature") or req.headers.get("X-Tokenade-Signature")
            assert sig.startswith("sha256=")

    def test_send_webhook_signature_correct(self, sharer, session):
        secret = "test_secret_123"
        config = ShareConfig(
            webhook_url="https://hooks.example.com/session",
            webhook_secret=secret,
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 200
            mock_resp.read.return_value = b'ok'
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            sharer.send_webhook(session, config)

            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))
            body = json.dumps(payload, separators=(",", ":")).encode()
            expected_sig = hmac.HMAC(secret.encode(), body, hashlib.sha256).hexdigest()
            # urllib.request.Request lowercases headers
            sig = req.headers.get("X-tokenade-signature") or req.headers.get("X-Tokenade-Signature")
            actual_sig = sig.replace("sha256=", "")
            assert actual_sig == expected_sig

    def test_send_webhook_http_error(self, sharer, session):
        import urllib.error

        config = ShareConfig(webhook_url="https://hooks.example.com/session")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://hooks.example.com/session",
                code=500,
                msg="Internal Server Error",
                hdrs=None,
                fp=MagicMock(read=MagicMock(return_value=b"error")),
            )

            success, msg = sharer.send_webhook(session, config)
            assert success is False
            assert "HTTP 500" in msg

    def test_send_webhook_connection_error(self, sharer, session):
        config = ShareConfig(webhook_url="https://hooks.example.com/session")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = ConnectionError("Connection refused")

            success, msg = sharer.send_webhook(session, config)
            assert success is False
            assert "Connection refused" in msg

    def test_send_webhook_http_non_200(self, sharer, session):
        config = ShareConfig(webhook_url="https://hooks.example.com/session")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.getcode.return_value = 403
            mock_resp.read.return_value = b"Forbidden"
            mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            success, msg = sharer.send_webhook(session, config)
            assert success is False
            assert "HTTP 403" in msg


class TestSessionSharerVersioning:
    @pytest.fixture
    def session(self):
        return {
            "version": "2.0",
            "site_name": "github",
            "cookies": [
                {"name": "user_session", "value": "abc", "domain": ".github.com", "path": "/"},
            ],
        }

    @pytest.fixture
    def sharer(self, tmp_path):
        return SessionSharer(storage_dir=str(tmp_path / "shared"))

    def test_create_multiple_versions(self, sharer, session):
        v1 = sharer.create_version(session, changes="Initial")
        v2 = sharer.create_version(session, changes="Added cookies")
        v3 = sharer.create_version(session, changes="Removed stale")

        versions = sharer.list_versions()
        assert len(versions) == 3
        assert versions[0]["changes"] == "Removed stale"
        assert versions[1]["changes"] == "Added cookies"
        assert versions[2]["changes"] == "Initial"

    def test_version_preserves_session_data(self, sharer, session):
        version_id = sharer.create_version(session, changes="Test preservation")
        loaded = sharer.load_version(version_id)
        assert loaded["site_name"] == session["site_name"]
        assert loaded["cookies"][0]["name"] == session["cookies"][0]["name"]

    def test_rollback_restores_session(self, sharer, session):
        v1_id = sharer.create_version(session, changes="Original")
        modified = {**session, "cookies": [{"name": "new_cookie", "value": "x", "domain": ".github.com"}]}
        sharer.create_version(modified, changes="Modified")

        rolled_back = sharer.rollback_version(v1_id)
        assert rolled_back["cookies"][0]["name"] == "user_session"

    def test_version_id_format(self, sharer, session):
        version_id = sharer.create_version(session, changes="Format check")
        parts = version_id.split("_")
        assert parts[0] == "github"
        assert len(parts) == 3

    def test_empty_version_list(self, sharer):
        versions = sharer.list_versions()
        assert versions == []

    def test_version_cookies_count(self, sharer, session):
        version_id = sharer.create_version(session, changes="Count check")
        version_path = sharer.versions_dir / f"{version_id}.json"
        with open(version_path) as f:
            data = json.load(f)
        assert data["cookies_count"] == len(session["cookies"])


class TestSessionSharerEdgeCases:
    @pytest.fixture
    def sharer(self, tmp_path):
        return SessionSharer(storage_dir=str(tmp_path / "shared"))

    @pytest.fixture
    def session(self):
        return {
            "version": "2.0",
            "site_name": "gmail",
            "cookies": [
                {"name": "SID", "value": "abc", "domain": ".google.com", "path": "/"},
            ],
        }

    def test_load_from_url_invalid_base64(self, sharer):
        result = sharer.load_from_url("tokenade://share/!!!invalid!!!")
        assert result is None

    def test_load_from_url_empty_payload(self, sharer):
        import base64
        payload = json.dumps({"id": "test"}).encode()
        b64 = base64.urlsafe_b64encode(payload).decode()
        result = sharer.load_from_url(f"tokenade://share/{b64}")
        assert result is None

    def test_revoke_nonexistent(self, sharer):
        # revoke_share is idempotent - returns True even if not found
        assert sharer.revoke_share("nonexistent") is True

    def test_list_empty(self, sharer):
        shares = sharer.list_shared()
        assert shares == []

    def test_share_link_url_format(self, sharer, session):
        url, session_id = sharer.create_share_link(session)
        assert url.startswith("tokenade://share/")
        payload_part = url[len("tokenade://share/"):]
        assert len(payload_part) > 0

    def test_load_shared_nonexistent(self, sharer):
        result = sharer.load_shared("nonexistent_id")
        assert result is None

    def test_large_session(self, sharer):
        cookies = [
            {"name": f"cookie_{i}", "value": f"val_{i}", "domain": ".example.com"}
            for i in range(500)
        ]
        session = {"version": "2.0", "site_name": "big_site", "cookies": cookies}
        url, session_id = sharer.create_share_link(session)
        loaded = sharer.load_from_url(url)
        assert len(loaded["cookies"]) == 500

    def test_generate_share_html_creates_file(self, sharer, session, tmp_path):
        output = str(tmp_path / "test_share.html")
        result = generate_share_html(session, output)
        assert Path(result).exists()
        content = Path(result).read_text()
        assert "gmail" in content
        assert "downloadSession" in content
