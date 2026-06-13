"""Tests for session sharer."""

import json
import time
import pytest
from pathlib import Path
from tokenade.core.importer.session_sharer import (
    SessionSharer,
    ShareConfig,
    SharedSession,
    generate_share_html,
)


class TestShareConfig:
    def test_default_config(self):
        config = ShareConfig()
        assert config.expiry_hours == 24
        assert config.max_uses == 0
        assert config.password_protected is False
        assert config.password is None

    def test_custom_config(self):
        config = ShareConfig(
            expiry_hours=48,
            max_uses=10,
            password_protected=True,
            password="secret",
        )
        assert config.expiry_hours == 48
        assert config.max_uses == 10
        assert config.password_protected is True
        assert config.password == "secret"


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
        # Password is embedded in URL, so load_from_url uses it automatically
        config = ShareConfig(password_protected=True, password="secret")
        url, session_id = sharer.create_share_link(session, config)
        # Load without providing password - it should use the one from URL
        loaded = sharer.load_from_url(url)
        assert loaded is not None

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
