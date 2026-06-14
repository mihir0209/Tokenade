"""Tests for batch operations module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tokenade.core.batch.operations import (
    BatchSiteConfig,
    BatchExportResult,
    BatchLoadResult,
    BatchExporter,
    BatchLoader,
    load_batch_config,
    generate_batch_report,
)


class TestBatchSiteConfig:
    def test_from_dict_full(self):
        data = {
            "name": "github",
            "url": "https://github.com",
            "domains": ["github.com", ".github.com"],
            "auth_cookies": ["logged_in", "user_session"],
            "validation_strategies": {"check_url": "https://github.com"},
        }
        config = BatchSiteConfig.from_dict(data)
        assert config.name == "github"
        assert config.url == "https://github.com"
        assert config.domains == ["github.com", ".github.com"]
        assert config.auth_cookies == ["logged_in", "user_session"]
        assert config.validation_strategies == {"check_url": "https://github.com"}

    def test_from_dict_defaults(self):
        config = BatchSiteConfig.from_dict({})
        assert config.name == ""
        assert config.url == ""
        assert config.domains == []
        assert config.auth_cookies == []
        assert config.validation_strategies == {}

    def test_from_dict_partial(self):
        data = {"name": "test", "domains": ["test.com"]}
        config = BatchSiteConfig.from_dict(data)
        assert config.name == "test"
        assert config.domains == ["test.com"]
        assert config.auth_cookies == []

    def test_dataclass_defaults(self):
        config = BatchSiteConfig(name="a", url="b")
        assert config.domains == []
        assert config.auth_cookies == []
        assert config.validation_strategies == {}


class TestBatchExportResult:
    def test_success(self):
        r = BatchExportResult(
            success=True, sites_exported=2, sites_total=3, cookies_total=50,
            results=[{"site": "a", "status": "success"}, {"site": "b", "status": "success"}],
            errors=[]
        )
        assert r.success is True
        assert r.sites_exported == 2
        assert r.errors == []

    def test_failure(self):
        r = BatchExportResult(
            success=False, sites_exported=0, sites_total=1, cookies_total=0,
            errors=["No profile found"]
        )
        assert r.success is False
        assert len(r.errors) == 1


class TestBatchLoadResult:
    def test_success(self):
        r = BatchLoadResult(
            success=True, sites_loaded=2, sites_total=2, cookies_injected=40
        )
        assert r.success is True

    def test_failure(self):
        r = BatchLoadResult(
            success=False, sites_loaded=0, sites_total=1, cookies_injected=0,
            errors=["Directory not found"]
        )
        assert r.success is False


class TestLoadBatchConfig:
    def test_load_list_config(self, tmp_path):
        config_data = [
            {"name": "github", "url": "https://github.com", "domains": ["github.com"]},
            {"name": "gmail", "url": "https://mail.google.com", "domains": ["google.com"]},
        ]
        config_file = tmp_path / "batch.json"
        config_file.write_text(json.dumps(config_data))

        configs = load_batch_config(str(config_file))
        assert len(configs) == 2
        assert configs[0].name == "github"
        assert configs[1].name == "gmail"

    def test_load_single_config(self, tmp_path):
        config_data = {"name": "github", "url": "https://github.com", "domains": ["github.com"]}
        config_file = tmp_path / "batch.json"
        config_file.write_text(json.dumps(config_data))

        configs = load_batch_config(str(config_file))
        assert len(configs) == 1
        assert configs[0].name == "github"

    def test_load_invalid_config(self, tmp_path):
        config_file = tmp_path / "batch.json"
        config_file.write_text('"just a string"')

        with pytest.raises(ValueError, match="Invalid config format"):
            load_batch_config(str(config_file))

    def test_load_empty_list(self, tmp_path):
        config_file = tmp_path / "batch.json"
        config_file.write_text("[]")

        configs = load_batch_config(str(config_file))
        assert configs == []


class TestGenerateBatchReport:
    def test_export_report(self):
        result = BatchExportResult(
            success=True, sites_exported=2, sites_total=3, cookies_total=75,
            results=[
                {"site": "github", "status": "success", "cookies": 50, "path": "/tmp/github"},
                {"site": "gmail", "status": "success", "cookies": 25, "path": "/tmp/gmail"},
                {"site": "slack", "status": "no_cookies", "cookies": 0},
            ],
        )
        report = generate_batch_report(result)
        assert "BATCH EXPORT REPORT" in report
        assert "2/3" in report
        assert "75" in report
        assert "github" in report
        assert "slack" in report

    def test_load_report(self):
        result = BatchLoadResult(
            success=True, sites_loaded=1, sites_total=2, cookies_injected=30,
            results=[
                {"file": "github.tokenade", "status": "success", "cookies": 30, "site": "github"},
                {"file": "empty.tokenade", "status": "failed", "error": "No cookies"},
            ],
            errors=["empty.tokenade: No cookies"],
        )
        report = generate_batch_report(result)
        assert "BATCH LOAD REPORT" in report
        assert "1/2" in report
        assert "30" in report
        assert "ERRORS:" in report
        assert "empty.tokenade" in report

    def test_export_report_with_errors(self):
        result = BatchExportResult(
            success=False, sites_exported=0, sites_total=2, cookies_total=0,
            results=[
                {"site": "a", "status": "error", "error": "extract failed"},
            ],
            errors=["a: extract failed"],
        )
        report = generate_batch_report(result)
        assert "ERRORS:" in report
        assert "extract failed" in report


class TestBatchExporter:
    @patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery")
    def test_no_profile_found(self, mock_discovery_cls):
        mock_discovery = MagicMock()
        mock_discovery.discover_all.return_value = {"firefox": []}
        mock_discovery_cls.return_value = mock_discovery

        exporter = BatchExporter()
        result = exporter.export_batch(
            browser="firefox",
            sites=[BatchSiteConfig(name="test", url="https://test.com", domains=["test.com"])],
            output_dir="/tmp/test",
        )
        assert result.success is False
        assert "No profile found" in result.errors[0]

    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.core.importer.cookie_extractor.CookieExtractor")
    @patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery")
    def test_export_with_cookies(self, mock_discovery_cls, mock_extractor_cls, mock_packager_cls, tmp_path):
        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.browser = "chrome"
        mock_profile.name = "Default"
        mock_profile.path = "/fake/chrome"
        mock_discovery.discover_all.return_value = {"chrome": [mock_profile]}
        mock_discovery_cls.return_value = mock_discovery

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"name": "session", "domain": "github.com", "value": "abc"},
            {"name": "other", "domain": "other.com", "value": "xyz"},
        ]
        mock_extractor_cls.return_value = mock_extractor

        mock_packager = MagicMock()
        mock_packager.package.return_value = {"cookies": []}
        mock_packager.save.return_value = str(tmp_path / "github_session")
        mock_packager_cls.return_value = mock_packager

        exporter = BatchExporter()
        result = exporter.export_batch(
            browser="chrome",
            sites=[BatchSiteConfig(name="github", url="https://github.com", domains=["github.com"])],
            output_dir=str(tmp_path / "output"),
        )
        assert result.success is True
        assert result.sites_exported == 1
        assert result.cookies_total == 1

    @patch("tokenade.core.importer.cookie_extractor.CookieExtractor")
    @patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery")
    def test_export_extraction_error(self, mock_discovery_cls, mock_extractor_cls, tmp_path):
        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.browser = "chrome"
        mock_profile.name = "Default"
        mock_profile.path = "/fake/chrome"
        mock_discovery.discover_all.return_value = {"chrome": [mock_profile]}
        mock_discovery_cls.return_value = mock_discovery

        mock_extractor = MagicMock()
        mock_extractor.extract.side_effect = Exception("DB locked")
        mock_extractor_cls.return_value = mock_extractor

        exporter = BatchExporter()
        result = exporter.export_batch(
            browser="chrome",
            sites=[BatchSiteConfig(name="test", url="https://test.com", domains=["test.com"])],
            output_dir=str(tmp_path / "output"),
        )
        assert result.success is False
        assert "Cookie extraction failed" in result.errors[0]


class TestBatchLoader:
    def test_load_nonexistent_dir(self):
        loader = BatchLoader()
        result = loader.load_batch(
            sessions_dir="/nonexistent/path",
            target_browser="chrome",
        )
        assert result.success is False
        assert "Directory not found" in result.errors[0]

    def test_load_empty_dir(self, tmp_path):
        loader = BatchLoader()
        result = loader.load_batch(
            sessions_dir=str(tmp_path),
            target_browser="chrome",
        )
        assert result.success is True
        assert result.sites_loaded == 0
        assert result.sites_total == 0

    @patch("tokenade.core.importer.session_loader.SessionLoader")
    def test_load_with_session_files(self, mock_loader_cls, tmp_path):
        session_file = tmp_path / "github.tokenade"
        session_file.write_text('{"cookies": []}')

        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True,
            "cookies_injected": 10,
            "site_name": "github",
        }
        mock_loader_cls.return_value = mock_loader

        loader = BatchLoader()
        result = loader.load_batch(
            sessions_dir=str(tmp_path),
            target_browser="chrome",
        )
        assert result.success is True
        assert result.sites_loaded == 1
        assert result.cookies_injected == 10
        mock_loader.close.assert_called_once()

    @patch("tokenade.core.importer.session_loader.SessionLoader")
    def test_load_with_error(self, mock_loader_cls, tmp_path):
        session_file = tmp_path / "bad.tokenade"
        session_file.write_text('{"cookies": []}')

        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": False,
            "error": "Invalid session",
        }
        mock_loader_cls.return_value = mock_loader

        loader = BatchLoader()
        result = loader.load_batch(
            sessions_dir=str(tmp_path),
            target_browser="chrome",
        )
        assert result.success is False
        assert len(result.errors) == 1
