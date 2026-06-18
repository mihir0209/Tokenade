"""Tests for session loader."""

import json
from tokenade.core.importer.session_loader import SessionLoader


class TestSessionLoader:
    def test_creation(self):
        loader = SessionLoader()
        assert loader is not None

    def test_load_valid_file(self, tmp_path):
        session = {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "session", "value": "abc", "domain": ".example.com", "path": "/"},
            ],
        }
        f = tmp_path / "test.tokenade"
        f.write_text(json.dumps(session))

        loader = SessionLoader()
        # load() returns a result dict, doesn't raise
        result = loader.load(str(f), validate=False)
        assert isinstance(result, dict)

    def test_load_nonexistent_file(self):
        loader = SessionLoader()
        result = loader.load("/nonexistent/file.tokenade", validate=False)
        assert result.get("success") is False

    def test_load_invalid_json(self, tmp_path):
        f = tmp_path / "bad.tokenade"
        f.write_text("not json {{{")

        loader = SessionLoader()
        result = loader.load(str(f), validate=False)
        assert result.get("success") is False

    def test_load_empty_file(self, tmp_path):
        f = tmp_path / "empty.tokenade"
        f.write_text("")

        loader = SessionLoader()
        result = loader.load(str(f), validate=False)
        assert result.get("success") is False

    def test_close(self):
        loader = SessionLoader()
        loader.close()  # Should not raise
