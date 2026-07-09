"""Session sharer QR and version-list edge cases.

Formerly test_session_sharer_coverage2 — unique paths.
"""

import os
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

from tokenade.core.importer.session_sharer import (
    SessionSharer,
    ShareConfig,
)


class TestCreateQrCode(unittest.TestCase):
    """Lines 193-224: create_qr_code requires qrcode module."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)
        self.session = {
            "version": "2.0",
            "site_name": "test_site",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}],
        }

    def test_create_qr_code_import_error(self):
        with patch.dict("sys.modules", {"qrcode": None}):
            with self.assertRaises(ImportError) as ctx:
                self.sharer.create_qr_code(self.session, os.path.join(self.tmpdir, "qr.png"))
            assert "qrcode is required" in str(ctx.exception)

    def test_create_qr_code_success(self):
        mock_qr_module = MagicMock()
        mock_qr_class = MagicMock()
        mock_img = MagicMock()
        mock_qr_class.return_value = mock_img
        mock_qr_module.QRCode = mock_qr_class
        mock_qr_module.constants.ERROR_CORRECT_M = 0

        with patch.dict("sys.modules", {"qrcode": mock_qr_module}):
            output_path = os.path.join(self.tmpdir, "qr.png")
            result = self.sharer.create_qr_code(self.session, output_path)

        assert result == output_path
        mock_qr_class.assert_called_once()
        mock_img.add_data.assert_called_once()
        mock_img.make.assert_called_once_with(fit=True)
        mock_img.make_image.assert_called_once()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestLoadSharedNoPassword(unittest.TestCase):
    """Lines 255-257: load_shared when password is required but not provided."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)
        self.session = {
            "version": "2.0",
            "site_name": "test_site",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}],
        }

    def test_load_shared_no_password(self):
        config = ShareConfig(password_protected=True, password="secret")
        _, session_id = self.sharer.create_share_link(self.session, config)

        result = self.sharer.load_shared(session_id, password=None)
        assert result is None

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestLoadSharedWrongPassword(unittest.TestCase):
    """Lines 259-261: load_shared with wrong password."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)
        self.session = {
            "version": "2.0",
            "site_name": "test_site",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}],
        }

    def test_load_shared_wrong_password(self):
        config = ShareConfig(password_protected=True, password="correct_password")
        _, session_id = self.sharer.create_share_link(self.session, config)

        result = self.sharer.load_shared(session_id, password="wrong_password")
        assert result is None

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestLoadFromUrlRaw(unittest.TestCase):
    """Line 281: load_from_url when share_url doesn't start with tokenade://share/."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)
        self.session = {
            "version": "2.0",
            "site_name": "test_site",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}],
        }

    def test_load_from_url_raw(self):
        # Create a valid share URL first, then strip the prefix
        url, _ = self.sharer.create_share_link(self.session)
        raw_payload = url[len("tokenade://share/"):]

        # load_from_url should handle raw base64 without the prefix
        result = self.sharer.load_from_url(raw_payload)
        assert result is not None
        assert result["site_name"] == "test_site"

    def test_load_from_url_raw_with_padding(self):
        url, _ = self.sharer.create_share_link(self.session)
        raw_payload = url[len("tokenade://share/"):]

        # Ensure padding is stripped (as _generate_share_url does)
        raw_payload = raw_payload.rstrip("=")
        result = self.sharer.load_from_url(raw_payload)
        assert result is not None

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestListSharedExpired(unittest.TestCase):
    """Lines 326-327: list_shared cleans up expired sessions."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)
        self.session = {
            "version": "2.0",
            "site_name": "test_site",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}],
        }

    def test_list_shared_expired(self):
        # Create a session that expires immediately
        config = ShareConfig(expiry_hours=0)
        _, session_id = self.sharer.create_share_link(self.session, config)
        time.sleep(0.1)

        # list_shared should skip expired and delete the file
        shared_list = self.sharer.list_shared()
        assert len(shared_list) == 0
        assert not (self.sharer.storage_dir / f"{session_id}.json").exists()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestListSharedBadJson(unittest.TestCase):
    """Lines 337-338: list_shared exception handling for bad JSON."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)

    def test_list_shared_bad_json(self):
        # Write a garbage .json file that will fail to parse
        bad_file = self.sharer.storage_dir / "bad_session.json"
        with open(bad_file, "w") as f:
            f.write("not valid json {{{")

        # Should not raise, just skip the bad file
        shared_list = self.sharer.list_shared()
        assert shared_list == []

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestRevokeShareException(unittest.TestCase):
    """Lines 348-349: revoke_share exception handling returns False."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)

    def test_revoke_share_exception(self):
        with patch.object(self.sharer, "_delete_shared", side_effect=OSError("disk error")):
            result = self.sharer.revoke_share("some_session_id")
            assert result is False

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestListVersionsException(unittest.TestCase):
    """Lines 544-545: list_versions exception handling for bad version files."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)

    def test_list_versions_bad_json(self):
        # Write a bad JSON file in the versions directory
        bad_file = self.sharer.versions_dir / "bad_version.json"
        with open(bad_file, "w") as f:
            f.write("{bad json")

        versions = self.sharer.list_versions()
        assert versions == []

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestLoadVersionException(unittest.TestCase):
    """Lines 560-561: load_version exception handling returns None."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)

    def test_load_version_corrupt_json(self):
        version_path = self.sharer.versions_dir / "corrupt_version.json"
        with open(version_path, "w") as f:
            f.write("{corrupt!")

        result = self.sharer.load_version("corrupt_version")
        assert result is None

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestLoadSharedCorruptFile(unittest.TestCase):
    """Lines 603-604: _load_shared exception handling returns None."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sharer = SessionSharer(storage_dir=self.tmpdir)

    def test_load_shared_corrupt_json(self):
        bad_file = self.sharer.storage_dir / "corrupt_session.json"
        with open(bad_file, "w") as f:
            f.write("{{{{not json")

        result = self.sharer._load_shared("corrupt_session")
        assert result is None

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
