"""
Comprehensive tests for tor_extractor.py — Tor Browser profile discovery,
extraction, and error handling.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from tokenade.core.importer.tor_extractor import (
    TorExtractor,
    TOR_PROFILE_PATHS,
)


class TestTORProfilePaths(unittest.TestCase):
    def test_has_linux(self):
        self.assertIn("Linux", TOR_PROFILE_PATHS)

    def test_has_darwin(self):
        self.assertIn("Darwin", TOR_PROFILE_PATHS)

    def test_has_windows(self):
        self.assertIn("Windows", TOR_PROFILE_PATHS)


class TestTorExtractorInit(unittest.TestCase):
    def test_init_with_path(self):
        ext = TorExtractor(profile_path="/tmp/fake")
        self.assertEqual(ext.profile_path, "/tmp/fake")
        self.assertIsNone(ext._extractor)

    def test_init_no_path_calls_find(self):
        with patch.object(
            TorExtractor, "_find_tor_profile", return_value="/found/path"
        ):
            ext = TorExtractor()
            self.assertEqual(ext.profile_path, "/found/path")

    def test_init_no_path_not_found(self):
        with patch.object(
            TorExtractor, "_find_tor_profile", return_value=None
        ):
            ext = TorExtractor()
            self.assertIsNone(ext.profile_path)


class TestTorExtractorFindProfile(unittest.TestCase):
    def test_found_at_known_path(self):
        ext = TorExtractor.__new__(TorExtractor)
        with (
            patch("os.path.expandvars", return_value="/fake/tor"),
            patch("os.path.expanduser", return_value="/fake/tor"),
            patch("os.path.exists", side_effect=lambda p: True),
        ):
            result = ext._find_tor_profile()
            self.assertEqual(result, "/fake/tor")

    def test_found_at_glob_path(self):
        ext = TorExtractor.__new__(TorExtractor)
        with (
            patch("os.path.expandvars", return_value="/nonexistent"),
            patch("os.path.expanduser", return_value="/nonexistent"),
            patch(
                "os.path.exists",
                side_effect=lambda p: "torbrowser" in p or "profile" in p,
            ),
            patch("platform.system", return_value="Linux"),
            patch("os.path.expanduser", return_value="/home/user/.torbrowser"),
            patch(
                "glob.glob",
                return_value=["/home/user/.torbrowser/profile.default"],
            ),
        ):
            result = ext._find_tor_profile()
            self.assertIsNotNone(result)

    def test_not_found(self):
        ext = TorExtractor.__new__(TorExtractor)
        with (
            patch("os.path.expandvars", return_value="/nonexistent"),
            patch("os.path.expanduser", return_value="/nonexistent"),
            patch("os.path.exists", return_value=False),
        ):
            result = ext._find_tor_profile()
            self.assertIsNone(result)

    def test_darwin_paths(self):
        ext = TorExtractor.__new__(TorExtractor)
        with (
            patch("platform.system", return_value="Darwin"),
            patch("os.path.expandvars", return_value="/nonexistent"),
            patch("os.path.expanduser", return_value="/nonexistent"),
            patch("os.path.exists", return_value=False),
        ):
            result = ext._find_tor_profile()
            self.assertIsNone(result)

    def test_windows_paths(self):
        ext = TorExtractor.__new__(TorExtractor)
        with (
            patch("platform.system", return_value="Windows"),
            patch("os.path.expandvars", return_value="/nonexistent"),
            patch("os.path.expanduser", return_value="/nonexistent"),
            patch("os.path.exists", return_value=False),
            patch.dict(
                os.environ, {"LOCALAPPDATA": "/local", "APPDATA": "/appdata"}
            ),
        ):
            result = ext._find_tor_profile()
            self.assertIsNone(result)


class TestTorExtractorExtract(unittest.TestCase):
    def test_no_profile(self):
        ext = TorExtractor(profile_path=None)
        result = ext.extract()
        self.assertEqual(result, [])

    def test_profile_not_exist(self):
        ext = TorExtractor(profile_path="/nonexistent/path")
        result = ext.extract()
        self.assertEqual(result, [])

    def test_extract_delegates_to_cookie_extractor(self):
        ext = TorExtractor(profile_path="/fake/tor")
        with patch("os.path.exists", return_value=True):
            mock_extractor = MagicMock()
            mock_extractor.extract_firefox.return_value = [
                {"name": "t", "value": "v"}
            ]
            with patch(
                "tokenade.core.importer.tor_extractor.CookieExtractor",
                return_value=mock_extractor,
            ):
                result = ext.extract()
                self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
