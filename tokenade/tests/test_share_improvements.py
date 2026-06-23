"""Tests for Phase 42: Session Sharing Improvements."""
import json
import tempfile
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_session(tmp_dir):
    session = {
        "site_name": "github",
        "cookies": [
            {"name": "user_session", "value": "abc123", "domain": ".github.com"},
        ],
        "local_storage": {},
        "session_storage": {},
    }
    path = tmp_dir / "github.tokenade"
    path.write_text(json.dumps(session))
    return path


class TestShareCLIEnhancements:
    """Test enhanced share CLI flags."""

    def test_share_parser_email_flags(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "share", "-s", "test.tokenade",
            "--email-to", "a@test.com,b@test.com",
            "--smtp-host", "smtp.test.com",
            "--webhook-url", "https://hook.test.com",
        ])
        assert args.email_to == "a@test.com,b@test.com"
        assert args.smtp_host == "smtp.test.com"
        assert args.webhook_url == "https://hook.test.com"

    def test_share_parser_password(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "share", "-s", "test.tokenade",
            "--password", "secret123",
        ])
        assert args.password == "secret123"


class TestImportCLI:
    """Test import command parser."""

    def test_import_parser(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "import", "tokenade://share/abc123",
        ])
        assert args.command == "import"
        assert args.url == "tokenade://share/abc123"
        assert args.password is None

    def test_import_parser_with_password(self):
        from tokenade.cli import _build_parser

        parser = _build_parser()
        args = parser.parse_args([
            "import", "tokenade://share/abc123",
            "--password", "secret",
            "--output", "out.tokenade",
        ])
        assert args.password == "secret"
        assert args.output == "out.tokenade"


class TestSessionSharerURL:
    """Test session share URL creation and loading."""

    def test_create_and_load_url(self, tmp_dir, sample_session):
        from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig
        from tokenade.core.importer.session_packager import SessionPackager

        packager = SessionPackager()
        session = packager.load(str(sample_session))

        sharer = SessionSharer()
        config = ShareConfig(expiry_hours=24, password="mypass")
        url, session_id = sharer.create_share_link(session, config)

        assert url.startswith("tokenade://share/")
        assert len(session_id) > 0

        # Load from URL
        loaded = sharer.load_from_url(url, password="mypass")
        assert loaded["site_name"] == "github"
        assert len(loaded["cookies"]) == 1

    def test_create_url_no_password(self, tmp_dir, sample_session):
        from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig
        from tokenade.core.importer.session_packager import SessionPackager

        packager = SessionPackager()
        session = packager.load(str(sample_session))

        sharer = SessionSharer()
        config = ShareConfig(expiry_hours=24)
        url, session_id = sharer.create_share_link(session, config)

        assert url.startswith("tokenade://share/")

        # Load without password
        loaded = sharer.load_from_url(url)
        assert loaded["site_name"] == "github"

    def test_wrong_password_fails(self, tmp_dir, sample_session):
        from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig
        from tokenade.core.importer.session_packager import SessionPackager

        packager = SessionPackager()
        session = packager.load(str(sample_session))

        sharer = SessionSharer()
        config = ShareConfig(expiry_hours=24, password="correct")
        url, _ = sharer.create_share_link(session, config)

        # load_from_url returns None on wrong password
        result = sharer.load_from_url(url, password="wrong")
        assert result is None


class TestShareExpiry:
    """Test share expiry and max uses."""

    def test_expired_share_fails(self, tmp_dir, sample_session):
        from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig
        from tokenade.core.importer.session_packager import SessionPackager

        packager = SessionPackager()
        session = packager.load(str(sample_session))

        sharer = SessionSharer()
        config = ShareConfig(expiry_hours=0)  # expires immediately
        url, session_id = sharer.create_share_link(session, config)

        import time
        time.sleep(0.1)

        # load_shared checks expiry, load_from_url just decrypts
        shared = sharer.load_shared(session_id)
        assert shared is None  # expired shares are filtered out

    def test_max_uses_enforced(self, tmp_dir, sample_session):
        from tokenade.core.importer.session_sharer import SessionSharer, ShareConfig
        from tokenade.core.importer.session_packager import SessionPackager

        packager = SessionPackager()
        session = packager.load(str(sample_session))

        sharer = SessionSharer()
        config = ShareConfig(expiry_hours=24, max_uses=2)
        url, session_id = sharer.create_share_link(session, config)

        # load_shared checks max_uses
        s1 = sharer.load_shared(session_id)
        assert s1 is not None
        s2 = sharer.load_shared(session_id)
        assert s2 is not None
        # Third use should fail
        s3 = sharer.load_shared(session_id)
        assert s3 is None
