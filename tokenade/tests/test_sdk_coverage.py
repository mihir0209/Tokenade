"""
Comprehensive tests for sdk/__init__.py — ExtractionResult, TokenadeClient
extract, load, health_check, share, list_sessions, export_playwright.
"""
import json
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
import tempfile
import os

from tokenade.sdk import ExtractionResult, TokenadeClient


class TestExtractionResult(unittest.TestCase):
    def test_defaults(self):
        result = ExtractionResult(success=False)
        self.assertFalse(result.success)
        self.assertIsNone(result.session_file)
        self.assertIsNone(result.session_data)
        self.assertEqual(result.cookie_count, 0)
        self.assertIsNone(result.error)

    def test_full_init(self):
        result = ExtractionResult(
            success=True, session_file="/path/to/file",
            session_data={"cookies": []}, cookie_count=42, error="none"
        )
        self.assertTrue(result.success)
        self.assertEqual(result.session_file, "/path/to/file")
        self.assertEqual(result.cookie_count, 42)


class TestTokenadeClientInit(unittest.TestCase):
    def test_default_init(self):
        client = TokenadeClient()
        self.assertTrue(client.sessions_dir.exists())

    def test_custom_sessions_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            self.assertEqual(client.sessions_dir, Path(tmpdir))


class TestTokenadeClientExtract(unittest.TestCase):
    def test_extract_no_profiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {}
                result = client.extract(browser="chrome")
                self.assertFalse(result.success)
                self.assertIn("No profiles found", result.error)

    def test_extract_no_cookies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            mock_profile = MagicMock()
            mock_profile.name = "Default"
            mock_profile.path = "/fake/chrome"
            with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {"chrome": [mock_profile]}
                with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as MockExtractor:
                    MockExtractor.return_value.extract.return_value = []
                    result = client.extract(browser="chrome")
                    self.assertFalse(result.success)
                    self.assertIn("No cookies extracted", result.error)

    def test_extract_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            mock_profile = MagicMock()
            mock_profile.name = "Default"
            mock_profile.path = "/fake/chrome"
            cookies = [{"name": "sid", "value": "v", "domain": ".github.com", "path": "/"}]
            session = {"cookies": cookies, "site_name": "github"}
            with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {"chrome": [mock_profile]}
                with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as MockExtractor:
                    MockExtractor.return_value.extract.return_value = cookies
                    with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
                        MockPackager.return_value.package.return_value = session
                        result = client.extract(browser="chrome", domains=["github.com"])
                        self.assertTrue(result.success)
                        self.assertEqual(result.cookie_count, 1)

    def test_extract_with_profile_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            mock_profile1 = MagicMock()
            mock_profile1.name = "Default"
            mock_profile1.path = "/fake/p1"
            mock_profile2 = MagicMock()
            mock_profile2.name = "Profile 1"
            mock_profile2.path = "/fake/p2"
            with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {"chrome": [mock_profile1, mock_profile2]}
                with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as MockExtractor:
                    MockExtractor.return_value.extract.return_value = [{"name": "t", "value": "v", "domain": ".x.com", "path": "/"}]
                    with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
                        MockPackager.return_value.package.return_value = {"cookies": [], "site_name": "test"}
                        result = client.extract(browser="chrome", profile="Profile 1")
                        self.assertTrue(result.success)

    def test_extract_with_output_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            mock_profile = MagicMock()
            mock_profile.name = "Default"
            mock_profile.path = "/fake/chrome"
            cookies = [{"name": "sid", "value": "v", "domain": ".github.com", "path": "/"}]
            with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {"chrome": [mock_profile]}
                with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as MockExtractor:
                    MockExtractor.return_value.extract.return_value = cookies
                    with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
                        MockPackager.return_value.package.return_value = {"cookies": [], "site_name": "github"}
                        out_path = os.path.join(tmpdir, "custom.tokenade")
                        result = client.extract(browser="chrome", output=out_path)
                        self.assertTrue(result.success)
                        self.assertEqual(result.session_file, out_path)

    def test_extract_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery", side_effect=RuntimeError("fail")):
                result = client.extract(browser="chrome")
                self.assertFalse(result.success)
                self.assertIn("fail", result.error)

    def test_extract_domain_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            mock_profile = MagicMock()
            mock_profile.name = "Default"
            mock_profile.path = "/fake/chrome"
            cookies = [{"name": "sid", "value": "v", "domain": ".github.com", "path": "/"}]
            with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {"chrome": [mock_profile]}
                with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as MockExtractor:
                    MockExtractor.return_value.extract.return_value = cookies
                    with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
                        MockPackager.return_value.package.return_value = {"cookies": [], "site_name": "github"}
                        result = client.extract(browser="chrome", domains=["github.com"])
                        self.assertTrue(result.success)

    def test_extract_unknown_domain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            mock_profile = MagicMock()
            mock_profile.name = "Default"
            mock_profile.path = "/fake/chrome"
            cookies = [{"name": "sid", "value": "v", "domain": ".example.com", "path": "/"}]
            with patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery") as MockDiscovery:
                MockDiscovery.return_value.discover_all.return_value = {"chrome": [mock_profile]}
                with patch("tokenade.core.importer.cookie_extractor.CookieExtractor") as MockExtractor:
                    MockExtractor.return_value.extract.return_value = cookies
                    with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
                        MockPackager.return_value.package.return_value = {"cookies": [], "site_name": "session"}
                        result = client.extract(browser="chrome", domains=["unknown.com"])
                        self.assertTrue(result.success)


class TestTokenadeClientLoad(unittest.TestCase):
    def test_load_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            session = {"cookies": [], "site_name": "test"}
            with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
                MockPackager.return_value.load.return_value = session
                result = client.load("/fake/session.tokenade")
                self.assertEqual(result, session)

    def test_load_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            with patch("tokenade.core.importer.session_packager.SessionPackager") as MockPackager:
                MockPackager.return_value.load.side_effect = RuntimeError("not found")
                result = client.load("/fake/tokenade")
                self.assertIsNone(result)


class TestTokenadeClientHealthCheck(unittest.TestCase):
    def test_health_check_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            session_file = os.path.join(tmpdir, "test.tokenade")
            with open(session_file, "w") as f:
                json.dump({"cookies": [{"name": "t", "value": "v"}]}, f)

            with patch("tokenade.core.refresh.health_checker.SessionHealthChecker") as MockChecker:
                mock_health = MagicMock()
                mock_health.healthy = True
                mock_health.health_score = 95
                mock_health.issues = []
                mock_health.recommendations = []
                MockChecker.return_value.check_session.return_value = mock_health
                with patch("tokenade.core.refresh.health_scorer.SessionHealthScorer") as MockScorer:
                    mock_score = MagicMock()
                    mock_score.total_score = 92
                    MockScorer.return_value.score.return_value = mock_score
                    result = client.health_check(session_file)
                    self.assertTrue(result["healthy"])
                    self.assertEqual(result["health_score"], 95)
                    self.assertEqual(result["owasp_score"], 92)

    def test_health_check_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            with patch("tokenade.core.refresh.health_checker.SessionHealthChecker", side_effect=RuntimeError("fail")):
                result = client.health_check("/nonexistent")
                self.assertFalse(result["healthy"])
                self.assertIn("error", result)


class TestTokenadeClientShare(unittest.TestCase):
    def test_share_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            session_file = os.path.join(tmpdir, "test.tokenade")
            with open(session_file, "w") as f:
                json.dump({"cookies": [], "site_name": "test"}, f)

            with patch("tokenade.core.importer.session_sharer.SessionSharer") as MockSharer:
                MockSharer.return_value.create_share_link.return_value = ("https://share.example.com/abc", {})
                result = client.share(session_file, password="secret", expiry_hours=48)
                self.assertEqual(result, "https://share.example.com/abc")

    def test_share_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            with patch("tokenade.core.importer.session_sharer.SessionSharer", side_effect=RuntimeError("fail")):
                result = client.share("/nonexistent")
                self.assertIsNone(result)


class TestTokenadeClientListSessions(unittest.TestCase):
    def test_list_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            mock_session = MagicMock()
            mock_session.path = "/test/path"
            mock_session.site_name = "github"
            mock_session.cookie_count = 15
            mock_session.created_at = "2026-01-01"
            mock_session.source_browser = "chrome"
            with patch("tokenade.core.importer.session_manager.SessionManager") as MockManager:
                MockManager.return_value.list_sessions.return_value = [mock_session]
                result = client.list_sessions()
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["site_name"], "github")


class TestTokenadeClientExportPlaywright(unittest.TestCase):
    def test_export_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            session_file = os.path.join(tmpdir, "test.tokenade")
            output_file = os.path.join(tmpdir, "output.json")
            with open(session_file, "w") as f:
                json.dump({"cookies": []}, f)

            with patch("tokenade.core.importer.format_exporter.FormatExporter") as MockExporter:
                MockExporter.return_value.to_playwright_storagestate.return_value = '{"origins":[]}'
                result = client.export_playwright(session_file, output_file)
                self.assertTrue(result)

    def test_export_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            client = TokenadeClient(sessions_dir=tmpdir)
            with patch("tokenade.core.importer.format_exporter.FormatExporter", side_effect=RuntimeError("fail")):
                result = client.export_playwright("/nonexistent", "/nonexistent_out")
                self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
