"""Tests for CLI commands."""

import json


class TestCLIDiff:
    def test_diff_identical_files(self, tmp_path):
        from tokenade.core.importer.session_comparator import SessionComparator

        session = {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [{"name": "s", "value": "v", "domain": ".x.com", "path": "/"}],
        }
        f1 = tmp_path / "a.tokenade"
        f2 = tmp_path / "b.tokenade"
        f1.write_text(json.dumps(session))
        f2.write_text(json.dumps(session))

        comparator = SessionComparator()
        result = comparator.compare_files(str(f1), str(f2))
        assert not result.has_changes

    def test_diff_different_files(self, tmp_path):
        from tokenade.core.importer.session_comparator import SessionComparator

        s1 = {"version": "2.0", "site_name": "a", "auth_status": "logged_in",
              "cookies": [{"name": "x", "value": "1", "domain": ".a.com", "path": "/"}]}
        s2 = {"version": "2.0", "site_name": "b", "auth_status": "logged_in",
              "cookies": [{"name": "x", "value": "2", "domain": ".a.com", "path": "/"}]}
        f1 = tmp_path / "a.tokenade"
        f2 = tmp_path / "b.tokenade"
        f1.write_text(json.dumps(s1))
        f2.write_text(json.dumps(s2))

        comparator = SessionComparator()
        result = comparator.compare_files(str(f1), str(f2))
        assert result.has_changes


class TestCLISetup:
    def test_credential_manager_integration(self):
        from tokenade.core.security.credentials import CredentialManager, AccountCredentials

        manager = CredentialManager(accounts_file="/tmp/test_tokenade_accounts.json")
        accounts = [
            AccountCredentials(number=1, email="test@example.com", password="secret",
                               profile_dir="/tmp/test_profile", site="google"),
        ]
        manager.save_accounts(accounts, use_keyring=False, encrypt_file=False)
        loaded = manager.load_accounts()
        assert len(loaded) == 1
        assert loaded[0].email == "test@example.com"

        import os
        os.unlink("/tmp/test_tokenade_accounts.json")


class TestCLIHealth:
    def test_health_checker(self, tmp_path):
        from tokenade.core.refresh.health_checker import SessionHealthChecker

        session = {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "valid", "value": "v", "domain": ".x.com",
                 "path": "/", "expires": 9999999999},
            ],
        }
        f = tmp_path / "test.tokenade"
        f.write_text(json.dumps(session))

        checker = SessionHealthChecker()
        health = checker.check_session(str(f))
        assert health.healthy is True
        assert health.health_score > 0.5

    def test_health_expired_cookies(self, tmp_path):
        from tokenade.core.refresh.health_checker import SessionHealthChecker

        session = {
            "version": "2.0",
            "site_name": "test",
            "auth_status": "logged_in",
            "cookies": [
                {"name": "expired", "value": "v", "domain": ".x.com",
                 "path": "/", "expires": 1000000000},
            ],
        }
        f = tmp_path / "test.tokenade"
        f.write_text(json.dumps(session))

        checker = SessionHealthChecker()
        health = checker.check_session(str(f))
        assert health.healthy is False
        assert any("expired" in i for i in health.issues)
