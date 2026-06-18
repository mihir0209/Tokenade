"""Tests targeting uncovered lines in batch/operations.py.

Uncovered lines:
  118       - profile filtering in BatchExporter
  158-160    - domain matching with leading dot
  167-173    - no cookies found for site
  197-200    - exception during site export
  282-289    - matching site config in BatchLoader
  316-319    - exception during session loading
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from tokenade.core.batch.operations import (
    BatchSiteConfig,
    BatchExporter,
    BatchLoader,
    BatchExportResult,
    BatchLoadResult,
    load_batch_config,
    generate_batch_report,
)


# ---------------------------------------------------------------------------
# BatchSiteConfig.from_dict
# ---------------------------------------------------------------------------

class TestBatchSiteConfig:
    def test_from_dict_full(self):
        data = {
            "name": "site1",
            "url": "https://example.com",
            "domains": ["example.com"],
            "auth_cookies": ["sid"],
            "validation_strategies": {"check": True},
        }
        cfg = BatchSiteConfig.from_dict(data)
        assert cfg.name == "site1"
        assert cfg.url == "https://example.com"
        assert cfg.domains == ["example.com"]
        assert cfg.auth_cookies == ["sid"]
        assert cfg.validation_strategies == {"check": True}

    def test_from_dict_defaults(self):
        cfg = BatchSiteConfig.from_dict({})
        assert cfg.name == ""
        assert cfg.url == ""
        assert cfg.domains == []
        assert cfg.auth_cookies == []
        assert cfg.validation_strategies == {}


# ---------------------------------------------------------------------------
# Line 118: profile filtering in export_batch
# ---------------------------------------------------------------------------

class TestBatchExporterProfileFilter:
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.core.importer.cookie_extractor.CookieExtractor")
    @patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery")
    def test_profile_filter_match(self, mock_disc_cls, mock_extractor_cls, mock_packager_cls, tmp_path):
        """Line 118: profile filter narrows matching profiles."""
        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.browser = "firefox"
        mock_profile.name = "default"
        mock_profile.path = tmp_path / "profile"
        mock_discovery.discover_all.return_value = {"firefox": [mock_profile]}
        mock_disc_cls.return_value = mock_discovery

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = []
        mock_extractor_cls.return_value = mock_extractor

        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager

        exporter = BatchExporter()
        site = BatchSiteConfig(name="site1", url="https://example.com", domains=["example.com"])
        result = exporter.export_batch(
            browser="firefox",
            sites=[site],
            output_dir=str(tmp_path / "out"),
            profile="default",
        )
        assert result.sites_exported == 0
        assert result.results[0]["status"] == "no_cookies"

    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.core.importer.cookie_extractor.CookieExtractor")
    @patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery")
    def test_no_profile_match(self, mock_disc_cls, mock_extractor_cls, mock_packager_cls, tmp_path):
        """No matching profile returns error."""
        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.browser = "chrome"
        mock_profile.name = "default"
        mock_discovery.discover_all.return_value = {"chrome": [mock_profile]}
        mock_disc_cls.return_value = mock_discovery

        exporter = BatchExporter()
        site = BatchSiteConfig(name="site1", url="https://example.com", domains=["example.com"])
        result = exporter.export_batch(
            browser="firefox",
            sites=[site],
            output_dir=str(tmp_path / "out"),
        )
        assert result.success is False
        assert "No profile found" in result.errors[0]


# ---------------------------------------------------------------------------
# Lines 158-160: domain matching with leading dot
# ---------------------------------------------------------------------------

class TestBatchExporterDomainMatching:
    def _make_cookie(self, domain):
        return {"name": "sid", "value": "val", "domain": domain}

    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.core.importer.cookie_extractor.CookieExtractor")
    @patch("tokenade.core.importer.browser_discovery.BrowserProfileDiscovery")
    def test_domain_with_leading_dot(self, mock_disc_cls, mock_extractor_cls, mock_packager_cls, tmp_path):
        """Lines 158-160: domain starts with '.' -> endswith check."""
        mock_discovery = MagicMock()
        mock_profile = MagicMock()
        mock_profile.browser = "firefox"
        mock_profile.name = "default"
        mock_profile.path = tmp_path / "profile"
        mock_discovery.discover_all.return_value = {"firefox": [mock_profile]}
        mock_disc_cls.return_value = mock_discovery

        cookies = [
            self._make_cookie("sub.example.com"),
            self._make_cookie("example.com"),
            self._make_cookie("other.com"),
        ]
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = cookies
        mock_extractor_cls.return_value = mock_extractor

        mock_packager = MagicMock()
        mock_packager.package.return_value = {"session": "data"}
        mock_packager.save.return_value = str(tmp_path / "out")
        mock_packager_cls.return_value = mock_packager

        exporter = BatchExporter()
        site = BatchSiteConfig(name="site1", url="https://example.com", domains=[".example.com"])
        result = exporter.export_batch(
            browser="firefox",
            sites=[site],
            output_dir=str(tmp_path / "out"),
            browser_path=str(tmp_path / "profile"),
        )
        assert result.success
        assert result.cookies_total == 2

    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.core.importer.cookie_extractor.CookieExtractor")
    def test_domain_without_leading_dot(self, mock_extractor_cls, mock_packager_cls, tmp_path):
        """Line 162: domain doesn't start with '.' -> equality check."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"name": "sid", "value": "val", "domain": "example.com"},
            {"name": "sid", "value": "val", "domain": "sub.example.com"},
        ]
        mock_extractor_cls.return_value = mock_extractor

        mock_packager = MagicMock()
        mock_packager.package.return_value = {"session": "data"}
        mock_packager.save.return_value = str(tmp_path / "out")
        mock_packager_cls.return_value = mock_packager

        exporter = BatchExporter()
        site = BatchSiteConfig(name="site1", url="https://example.com", domains=["example.com"])
        result = exporter.export_batch(
            browser="firefox",
            sites=[site],
            output_dir=str(tmp_path / "out"),
            browser_path=str(tmp_path / "profile"),
        )
        assert result.success
        assert result.cookies_total == 2


# ---------------------------------------------------------------------------
# Lines 167-173: no cookies found for site
# ---------------------------------------------------------------------------

class TestBatchExporterNoCookies:
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.core.importer.cookie_extractor.CookieExtractor")
    def test_no_cookies_for_site(self, mock_extractor_cls, mock_packager_cls, tmp_path):
        """Lines 167-173: no cookies found for a site."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"name": "sid", "value": "val", "domain": "other.com"},
        ]
        mock_extractor_cls.return_value = mock_extractor

        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager

        exporter = BatchExporter()
        site = BatchSiteConfig(name="site1", url="https://example.com", domains=["example.com"])
        result = exporter.export_batch(
            browser="firefox",
            sites=[site],
            output_dir=str(tmp_path / "out"),
            browser_path=str(tmp_path / "profile"),
        )
        assert result.success
        assert result.sites_exported == 0
        assert result.results[0]["status"] == "no_cookies"


# ---------------------------------------------------------------------------
# Lines 197-200: exception during site export
# ---------------------------------------------------------------------------

class TestBatchExporterException:
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("tokenade.core.importer.cookie_extractor.CookieExtractor")
    def test_exception_during_export(self, mock_extractor_cls, mock_packager_cls, tmp_path):
        """Lines 197-200: exception during site processing."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [
            {"name": "sid", "value": "val", "domain": "example.com"},
        ]
        mock_extractor_cls.return_value = mock_extractor

        mock_packager = MagicMock()
        mock_packager.package.side_effect = RuntimeError("packager broke")
        mock_packager_cls.return_value = mock_packager

        exporter = BatchExporter()
        site = BatchSiteConfig(name="site1", url="https://example.com", domains=["example.com"])
        result = exporter.export_batch(
            browser="firefox",
            sites=[site],
            output_dir=str(tmp_path / "out"),
            browser_path=str(tmp_path / "profile"),
        )
        assert result.success is False
        assert len(result.errors) == 1
        assert "site1" in result.errors[0]
        assert result.results[0]["status"] == "error"


# ---------------------------------------------------------------------------
# Lines 282-289: matching site config in load_batch
# ---------------------------------------------------------------------------

class TestBatchLoaderSiteConfigMatch:
    @patch("tokenade.core.importer.session_loader.SessionLoader")
    def test_matching_site_config(self, mock_loader_cls, tmp_path):
        """Lines 282-289: find matching site config for session file."""
        session_file = tmp_path / "site1_session.tokenade"
        session_file.write_text("{}")

        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True,
            "cookies_injected": 5,
            "site_name": "site1",
        }
        mock_loader_cls.return_value = mock_loader

        site_config = BatchSiteConfig(
            name="site1",
            url="https://example.com",
            domains=["example.com"],
            validation_strategies={"check": True},
        )

        loader = BatchLoader()
        result = loader.load_batch(
            sessions_dir=str(tmp_path),
            target_browser="firefox",
            site_configs=[site_config],
        )
        assert result.success
        assert result.cookies_injected == 5

    @patch("tokenade.core.importer.session_loader.SessionLoader")
    def test_no_matching_site_config(self, mock_loader_cls, tmp_path):
        """No matching site config -> site_config remains None."""
        session_file = tmp_path / "other_session.tokenade"
        session_file.write_text("{}")

        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True,
            "cookies_injected": 3,
            "site_name": "other",
        }
        mock_loader_cls.return_value = mock_loader

        site_config = BatchSiteConfig(
            name="site1",
            url="https://example.com",
            domains=["example.com"],
        )

        loader = BatchLoader()
        result = loader.load_batch(
            sessions_dir=str(tmp_path),
            target_browser="firefox",
            site_configs=[site_config],
        )
        assert result.success
        call_kwargs = mock_loader.load.call_args[1]
        assert call_kwargs["site_config"] is None


# ---------------------------------------------------------------------------
# Lines 316-319: exception during session loading
# ---------------------------------------------------------------------------

class TestBatchLoaderException:
    @patch("tokenade.core.importer.session_loader.SessionLoader")
    def test_exception_during_load(self, mock_loader_cls, tmp_path):
        """Lines 316-319: exception during session file loading."""
        session_file = tmp_path / "bad_session.tokenade"
        session_file.write_text("{}")

        mock_loader = MagicMock()
        mock_loader.load.side_effect = RuntimeError("load failed")
        mock_loader_cls.return_value = mock_loader

        loader = BatchLoader()
        result = loader.load_batch(
            sessions_dir=str(tmp_path),
            target_browser="firefox",
        )
        assert result.success is False
        assert len(result.errors) == 1
        assert "bad_session.tokenade" in result.errors[0]
        assert result.results[0]["status"] == "error"


# ---------------------------------------------------------------------------
# load_batch_config
# ---------------------------------------------------------------------------

class TestLoadBatchConfig:
    def test_load_list_config(self, tmp_path):
        config_file = tmp_path / "batch.json"
        config_file.write_text(json.dumps([
            {"name": "s1", "url": "https://a.com", "domains": ["a.com"]},
            {"name": "s2", "url": "https://b.com", "domains": ["b.com"]},
        ]))
        configs = load_batch_config(str(config_file))
        assert len(configs) == 2
        assert configs[0].name == "s1"

    def test_load_single_dict_config(self, tmp_path):
        config_file = tmp_path / "batch.json"
        config_file.write_text(json.dumps({
            "name": "s1", "url": "https://a.com", "domains": ["a.com"],
        }))
        configs = load_batch_config(str(config_file))
        assert len(configs) == 1

    def test_invalid_config_format(self, tmp_path):
        config_file = tmp_path / "batch.json"
        config_file.write_text('"just a string"')
        with pytest.raises(ValueError, match="Invalid config format"):
            load_batch_config(str(config_file))


# ---------------------------------------------------------------------------
# generate_batch_report
# ---------------------------------------------------------------------------

class TestGenerateBatchReport:
    def test_export_report(self):
        result = BatchExportResult(
            success=True,
            sites_exported=2,
            sites_total=3,
            cookies_total=50,
            results=[
                {"site": "a", "status": "success", "cookies": 30, "path": "/a.tokenade"},
                {"site": "b", "status": "success", "cookies": 20},
                {"site": "c", "status": "no_cookies", "cookies": 0},
            ],
            errors=["d: some error"],
        )
        report = generate_batch_report(result)
        assert "BATCH EXPORT REPORT" in report
        assert "2/3" in report
        assert "50" in report
        assert "ERRORS" in report
        assert "d: some error" in report

    def test_load_report(self):
        result = BatchLoadResult(
            success=True,
            sites_loaded=1,
            sites_total=2,
            cookies_injected=10,
            results=[
                {"file": "a.tokenade", "status": "success", "cookies": 10, "site": "a"},
                {"file": "b.tokenade", "status": "failed", "error": "bad"},
            ],
            errors=["b.tokenade: bad"],
        )
        report = generate_batch_report(result)
        assert "BATCH LOAD REPORT" in report
        assert "1/2" in report
        assert "ERRORS" in report
