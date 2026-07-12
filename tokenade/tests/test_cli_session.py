"""Tests for CLI session commands."""

import json
import pytest
from unittest.mock import patch, MagicMock
from argparse import Namespace

from tokenade.cli.session import (
    cmd_extract,
    cmd_load,
    cmd_transfer,
    cmd_inject_profile,
)
from tokenade.cli.session_export import cmd_export


def _make_session_file(tmp_path, name="test", cookies=None, auth_status="logged_in",
                       site_name=None):
    if cookies is None:
        cookies = [{"name": "sid", "value": "abc", "domain": ".google.com"}]
    data = {
        "cookies": cookies,
        "site_name": site_name or name,
        "auth_status": auth_status,
    }
    f = tmp_path / f"{name}.tokenade"
    f.write_text(json.dumps(data))
    return f


def _make_account(number=1, email="test@gmail.com", profile_dir=None):
    account = MagicMock()
    account.number = number
    account.email = email
    account.profile_dir = profile_dir
    return account


def _make_mock_session(tokens=None, cookies=None, auth_status_value="logged_in"):
    session = MagicMock()
    session.tokens = tokens or []
    session.cookies = cookies or [{"name": "sid", "value": "abc", "domain": ".google.com"}]
    session.auth_status.value = auth_status_value
    session.get_token.return_value = MagicMock(
        to_dict=MagicMock(return_value={"token_type": "access_token", "value": "tok123"})
    )
    return session


def _export_args(tmp_path=None, **overrides):
    defaults = dict(
        list_profiles=False, browser_path=str(tmp_path / "profile") if tmp_path else None,
        browser_name="chrome", profile="Default", site_config=None,
        domains=None, extract_local_storage=False, local_storage_origin=None,
        file_path=None, format=None, output=None,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def _setup_export_mocks(mock_disc, mock_config, mock_ce, mock_sp, tmp_path):
    mock_disc.discover_all.return_value = {}
    mock_config.get.return_value = None
    mock_ce.extract.return_value = [
        {"name": "sid", "value": "abc", "domain": ".google.com"}
    ]
    mock_sp.package.return_value = {
        "site_name": "google",
        "auth_status": "logged_in",
        "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
        "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
    }
    mock_sp.save.return_value = str(tmp_path / "session.tokenade")
    mock_sp.get_summary.return_value = "Summary"


# ── cmd_extract ──────────────────────────────────────────────────────────────

class TestCmdExtract:
    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_accounts_encrypted(self, mock_cm_cls, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.side_effect = ValueError("encrypted")
        mock_cm_cls.return_value = mock_cm
        cmd_extract(Namespace(visible=False))
        assert "encrypted" in capsys.readouterr().out.lower()

    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_no_accounts(self, mock_cm_cls, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.return_value = []
        mock_cm_cls.return_value = mock_cm
        cmd_extract(Namespace(visible=False))
        assert "no accounts" in capsys.readouterr().out.lower()

    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_profile_not_found(self, mock_cm_cls, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.return_value = [_make_account(profile_dir="/nonexistent")]
        mock_cm_cls.return_value = mock_cm
        with pytest.raises(SystemExit) as ei:
            cmd_extract(Namespace(visible=False))
        assert ei.value.code == 1
        assert "profile not found" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_success_with_token(self, mock_cm_cls, mock_bf_cls, mock_gh_cls,
                                        tmp_path, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.return_value = [_make_account(profile_dir=str(tmp_path))]
        mock_cm_cls.return_value = mock_cm

        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser

        mock_session = _make_mock_session(tokens=[MagicMock(token_type="access_token")])
        mock_handler = MagicMock()
        mock_handler.get_session.return_value = mock_session
        mock_handler.extract_tokens.return_value = [MagicMock(token_type="access_token")]
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)

        cmd_extract(Namespace(visible=False))
        output = capsys.readouterr().out
        assert "extraction complete" in output.lower()
        mock_browser.close.assert_called_once()

    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_success_no_tokens(self, mock_cm_cls, mock_bf_cls, mock_gh_cls,
                                       tmp_path, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.return_value = [_make_account(profile_dir=str(tmp_path))]
        mock_cm_cls.return_value = mock_cm

        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser

        mock_session = _make_mock_session(tokens=[])
        mock_handler = MagicMock()
        mock_handler.get_session.return_value = mock_session
        mock_handler.extract_tokens.return_value = []
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)

        cmd_extract(Namespace(visible=False))
        assert "extraction complete" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_browser_exception(self, mock_cm_cls, mock_bf_cls, mock_gh_cls,
                                       tmp_path, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.return_value = [_make_account(profile_dir=str(tmp_path))]
        mock_cm_cls.return_value = mock_cm

        mock_browser = MagicMock()
        mock_browser.launch.side_effect = RuntimeError("browser crash")
        mock_bf_cls.create.return_value = mock_browser

        with pytest.raises(SystemExit) as ei:
            cmd_extract(Namespace(visible=False))
        assert ei.value.code == 1
        output = capsys.readouterr().out
        assert "extraction" in output.lower()
        mock_browser.close.assert_called_once()

    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_default_profile_dir(self, mock_cm_cls, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.return_value = [_make_account(profile_dir=None)]
        mock_cm_cls.return_value = mock_cm
        with pytest.raises(SystemExit) as ei:
            cmd_extract(Namespace(visible=False))
        assert ei.value.code == 1
        assert "profile not found" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_visible_mode(self, mock_cm_cls, mock_bf_cls, mock_gh_cls,
                                  tmp_path, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.return_value = [_make_account(profile_dir=str(tmp_path))]
        mock_cm_cls.return_value = mock_cm

        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.get_session.return_value = _make_mock_session(tokens=[])
        mock_handler.extract_tokens.return_value = []
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)

        cmd_extract(Namespace(visible=True))
        call_kwargs = mock_bf_cls.create.call_args[1]
        assert call_kwargs.get("headless") is False

    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_saves_token_file(self, mock_cm_cls, mock_bf_cls, mock_gh_cls,
                                      tmp_path, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.return_value = [_make_account(profile_dir=str(tmp_path))]
        mock_cm_cls.return_value = mock_cm

        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser

        token_obj = MagicMock()
        token_obj.token_type = "access_token"
        token_obj.value = "tok123"

        mock_session = _make_mock_session(tokens=[token_obj])
        mock_handler = MagicMock()
        mock_handler.get_session.return_value = mock_session
        mock_handler.extract_tokens.return_value = [token_obj]
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)

        with patch("tokenade.cli.session.Path"):
            real_path = tmp_path / "sessions"
            real_path.mkdir(exist_ok=True)
            cmd_extract(Namespace(visible=False))
        output = capsys.readouterr().out
        assert "extraction complete" in output.lower()

    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    @patch("tokenade.core.security.credentials.CredentialManager")
    def test_extract_success_summary(self, mock_cm_cls, mock_bf_cls, mock_gh_cls,
                                     tmp_path, capsys):
        mock_cm = MagicMock()
        mock_cm.load_accounts.return_value = [
            _make_account(number=1, profile_dir=str(tmp_path)),
            _make_account(number=2, email="two@gmail.com", profile_dir=str(tmp_path)),
        ]
        mock_cm_cls.return_value = mock_cm

        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser

        mock_session = _make_mock_session(tokens=[])
        mock_handler = MagicMock()
        mock_handler.get_session.return_value = mock_session
        mock_handler.extract_tokens.return_value = []
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)

        cmd_extract(Namespace(visible=False))
        output = capsys.readouterr().out
        assert "successful:" in output.lower()


# ── cmd_export ───────────────────────────────────────────────────────────────

class TestCmdExport:
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_list_profiles(self, mock_disc_cls, capsys):
        mock_disc = MagicMock()
        profile = MagicMock()
        profile.browser = "chrome"
        profile.name = "Default"
        profile.path = "/home/user/.config/chrome/Default"
        profile.last_used = "2024-01-01"
        mock_disc.discover_all.return_value = {"chrome": [profile]}
        mock_disc_cls.return_value = mock_disc
        cmd_export(Namespace(list_profiles=True, browser_path=None, browser_name=None,
                             profile=None, site_config=None, domains=None,
                             extract_local_storage=False, local_storage_origin=None,
                             file_path=None, format=None, output=None))
        output = capsys.readouterr().out
        assert "chrome" in output.lower() or "profile" in output.lower()

    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_list_profiles_empty(self, mock_disc_cls, capsys):
        mock_disc = MagicMock()
        mock_disc.discover_all.return_value = {}
        mock_disc_cls.return_value = mock_disc
        cmd_export(Namespace(list_profiles=True, browser_path=None, browser_name=None,
                             profile=None, site_config=None, domains=None,
                             extract_local_storage=False, local_storage_origin=None,
                             file_path=None, format=None, output=None))
        assert "no browser profiles" in capsys.readouterr().out.lower()

    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_no_browser_path(self, mock_disc_cls, mock_config_cls, capsys):
        mock_disc = MagicMock()
        mock_disc.discover_all.return_value = {}
        mock_disc_cls.return_value = mock_disc
        mock_config = MagicMock()
        mock_config.get.return_value = None
        mock_config_cls.return_value = mock_config
        cmd_export(_export_args(None, browser_path=None, browser_name="unknown"))
        output = capsys.readouterr().out
        assert "no browser path" in output.lower() or "no profile found" in output.lower()

    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_profile_not_found(self, mock_disc_cls, mock_config_cls, capsys):
        mock_disc = MagicMock()
        p = MagicMock()
        p.browser = "firefox"
        p.name = "Default"
        mock_disc.discover_all.return_value = {"firefox": [p]}
        mock_disc_cls.return_value = mock_disc
        mock_config = MagicMock()
        mock_config.get.return_value = None
        mock_config_cls.return_value = mock_config
        cmd_export(_export_args(None, browser_path=None, browser_name="safari"))
        assert "no profile found" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_success(self, mock_disc_cls, mock_config_cls, mock_ce_cls,
                            mock_sp_cls, tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        _setup_export_mocks(mock_disc_cls.return_value, mock_config_cls.return_value,
                            mock_ce_cls.return_value, mock_sp_cls.return_value, tmp_path)
        cmd_export(_export_args(tmp_path))
        assert "exported" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_with_domain_filter(self, mock_disc_cls, mock_config_cls,
                                       mock_ce_cls, mock_sp_cls, tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"},
            {"name": "other", "value": "xyz", "domain": ".example.com"},
        ]
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path, domains="google.com"))
        assert "filtered" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_with_site_config(self, mock_disc_cls, mock_config_cls,
                                     mock_ce_cls, mock_sp_cls, tmp_path, capsys):
        config_file = tmp_path / "site.json"
        config_file.write_text(json.dumps({"domains": ["github.com"]}))
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "logged", "value": "1", "domain": ".github.com"},
            {"name": "other", "value": "2", "domain": ".other.com"},
        ]
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "github", "auth_status": "logged_in",
            "cookies": [{"name": "logged", "value": "1", "domain": ".github.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path, site_config=str(config_file)))
        assert "exported" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_extraction_exception(self, mock_disc_cls, mock_config_cls,
                                         mock_ce_cls, mock_sp_cls, tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.side_effect = RuntimeError("db locked")
        with pytest.raises(SystemExit) as ei:
            cmd_export(_export_args(tmp_path))
        assert ei.value.code == 1
        assert "extraction failed" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_no_cookies(self, mock_disc_cls, mock_config_cls,
                               mock_ce_cls, mock_sp_cls, tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = []
        cmd_export(_export_args(tmp_path))
        assert "no cookies" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_file_path_mode(self, mock_disc_cls, mock_config_cls,
                                   mock_ce_cls, mock_sp_cls, tmp_path, capsys):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("dummy")
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract_from_file.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"}
        ]
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path, file_path=str(cookie_file), format="netscape"))
        assert "exported" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.LocalStorageExtractor")
    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_with_local_storage(self, mock_disc_cls, mock_config_cls,
                                       mock_ce_cls, mock_sp_cls, mock_ls_cls,
                                       tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"}
        ]
        mock_ls_cls.return_value.extract.return_value = {"https://google.com": {"key": "val"}}
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 1},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path, extract_local_storage=True,
                                local_storage_origin="https://google.com"))
        output = capsys.readouterr().out
        assert "exported" in output.lower() or "localstorage" in output.lower()

    @patch("tokenade.cli.session_export.LocalStorageExtractor")
    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_local_storage_list_origins(self, mock_disc_cls, mock_config_cls,
                                               mock_ce_cls, mock_sp_cls, mock_ls_cls,
                                               tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"}
        ]
        mock_ls_cls.return_value.list_origins.return_value = [
            "https://google.com", "https://accounts.google.com"
        ]
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path, extract_local_storage=True))
        output = capsys.readouterr().out
        assert "origins" in output.lower() or "exported" in output.lower()

    @patch("tokenade.cli.session_export.LocalStorageExtractor")
    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_local_storage_no_origins(self, mock_disc_cls, mock_config_cls,
                                             mock_ce_cls, mock_sp_cls, mock_ls_cls,
                                             tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"}
        ]
        mock_ls_cls.return_value.list_origins.return_value = []
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path, extract_local_storage=True))
        assert "no localstorage" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.LocalStorageExtractor")
    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_local_storage_exception(self, mock_disc_cls, mock_config_cls,
                                            mock_ce_cls, mock_sp_cls, mock_ls_cls,
                                            tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"}
        ]
        mock_ls_cls.return_value.extract.side_effect = RuntimeError("browser locked")
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path, extract_local_storage=True,
                                local_storage_origin="https://google.com"))
        output = capsys.readouterr().out
        assert "skipped" in output.lower() or "exported" in output.lower()

    @patch("tokenade.cli.session_export.LocalStorageExtractor")
    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_no_ls_extract_matching_origins(self, mock_disc_cls, mock_config_cls,
                                                   mock_ce_cls, mock_sp_cls, mock_ls_cls,
                                                   tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"}
        ]
        mock_ls_cls.return_value.list_origins.return_value = ["https://google.com"]
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path))
        output = capsys.readouterr().out
        assert "localstorage" in output.lower() or "exported" in output.lower()

    @patch("tokenade.cli.session_export.LocalStorageExtractor")
    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_no_ls_no_matching_origins(self, mock_disc_cls, mock_config_cls,
                                              mock_ce_cls, mock_sp_cls, mock_ls_cls,
                                              tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"}
        ]
        mock_ls_cls.return_value.list_origins.return_value = ["https://example.com"]
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path))
        assert "exported" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.LocalStorageExtractor")
    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_ls_exception_list_origins(self, mock_disc_cls, mock_config_cls,
                                              mock_ce_cls, mock_sp_cls, mock_ls_cls,
                                              tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"}
        ]
        mock_ls_cls.return_value.list_origins.side_effect = RuntimeError("db locked")
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path))
        assert "exported" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_domain_filter_with_dot_prefix(self, mock_disc_cls, mock_config_cls,
                                                  mock_ce_cls, mock_sp_cls, tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"},
            {"name": "other", "value": "xyz", "domain": "google.com"},
            {"name": "third", "value": "123", "domain": ".example.com"},
        ]
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [
                {"name": "sid", "value": "abc", "domain": ".google.com"},
                {"name": "other", "value": "xyz", "domain": "google.com"},
            ],
            "metadata": {"cookie_count": 2, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path, domains=".google.com"))
        assert "filtered" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_site_config_list(self, mock_disc_cls, mock_config_cls,
                                     mock_ce_cls, mock_sp_cls, tmp_path, capsys):
        config_file = tmp_path / "sites.json"
        config_file.write_text(json.dumps([
            {"domains": ["github.com"]},
            {"domains": ["gitlab.com"]},
        ]))
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "logged", "value": "1", "domain": ".github.com"},
        ]
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "github", "auth_status": "logged_in",
            "cookies": [{"name": "logged", "value": "1", "domain": ".github.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 0},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        cmd_export(_export_args(tmp_path, site_config=str(config_file)))
        assert "exported" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session_export.SessionPackager")
    @patch("tokenade.cli.session_export.CookieExtractor")
    @patch("tokenade.core.config.load_config")
    @patch("tokenade.cli.session_export.BrowserProfileDiscovery")
    def test_export_with_local_storage_count(self, mock_disc_cls, mock_config_cls,
                                             mock_ce_cls, mock_sp_cls, tmp_path, capsys):
        mock_config_cls.return_value = MagicMock()
        mock_config_cls.return_value.get.return_value = None
        mock_disc_cls.return_value.discover_all.return_value = {}
        mock_ce_cls.return_value.extract.return_value = [
            {"name": "sid", "value": "abc", "domain": ".google.com"}
        ]
        mock_sp_cls.return_value.package.return_value = {
            "site_name": "google", "auth_status": "logged_in",
            "cookies": [{"name": "sid", "value": "abc", "domain": ".google.com"}],
            "metadata": {"cookie_count": 1, "critical_cookie_count": 1, "local_storage_count": 5},
        }
        mock_sp_cls.return_value.save.return_value = str(tmp_path / "session.tokenade")
        mock_sp_cls.return_value.get_summary.return_value = "Summary"
        with patch("tokenade.cli.session_export.LocalStorageExtractor") as mock_ls_cls:
            mock_ls = MagicMock()
            mock_ls.extract.return_value = {"k": "v"}
            mock_ls_cls.return_value = mock_ls
            cmd_export(_export_args(tmp_path, extract_local_storage=True,
                                    local_storage_origin="https://google.com"))
        output = capsys.readouterr().out
        assert "localstorage" in output.lower()


# ── cmd_load ─────────────────────────────────────────────────────────────────

class TestCmdLoad:
    def test_load_file_not_found(self, capsys):
        args = Namespace(file="/nonexistent/session.tokenade", site_config=None,
                         fingerprint="default", stealth_level="maximum",
                         validate=True, visible=False, profile_dir=None,
                         no_local_storage=False, runtime=False)
        cmd_load(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_success(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True, "site_name": "google",
            "cookies_injected": 5, "cookies_total": 5,
            "local_storage_injected": 0, "local_storage_total": 0,
        }
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=None, fingerprint="default",
                           stealth_level="maximum", validate=True, visible=False,
                           profile_dir=None, no_local_storage=False, runtime=False))
        output = capsys.readouterr().out
        assert "loaded successfully" in output.lower() or "session loaded" in output.lower()
        mock_loader.close.assert_called_once()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_with_local_storage(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True, "site_name": "google",
            "cookies_injected": 5, "cookies_total": 5,
            "local_storage_injected": 3, "local_storage_total": 5,
        }
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=None, fingerprint="default",
                           stealth_level="maximum", validate=True, visible=False,
                           profile_dir=None, no_local_storage=False, runtime=False))
        assert "localstorage" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_with_validation(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True, "site_name": "google",
            "cookies_injected": 5, "cookies_total": 5,
            "validation": {"auth_status": "logged_in", "valid": True},
        }
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=None, fingerprint="default",
                           stealth_level="maximum", validate=True, visible=False,
                           profile_dir=None, no_local_storage=False, runtime=False))
        assert "valid" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_with_runtime(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True, "site_name": "google",
            "cookies_injected": 5, "cookies_total": 5,
        }
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=None, fingerprint="default",
                           stealth_level="maximum", validate=False, visible=False,
                           profile_dir=None, no_local_storage=False, runtime=True))
        assert "runtime" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_failure(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": False, "error": "Browser launch failed",
        }
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=None, fingerprint="default",
                           stealth_level="maximum", validate=False, visible=False,
                           profile_dir=None, no_local_storage=False, runtime=False))
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_exception(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_loader = MagicMock()
        mock_loader.load.side_effect = RuntimeError("corrupt file")
        mock_loader_cls.return_value = mock_loader
        with pytest.raises(SystemExit) as ei:
            cmd_load(Namespace(file=str(f), site_config=None, fingerprint="default",
                               stealth_level="maximum", validate=False, visible=False,
                               profile_dir=None, no_local_storage=False, runtime=False))
        assert ei.value.code == 1
        assert "failed" in capsys.readouterr().out.lower()
        mock_loader.close.assert_called_once()

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_no_local_storage_flag(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True, "site_name": "google",
            "cookies_injected": 5, "cookies_total": 5,
        }
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=None, fingerprint="default",
                           stealth_level="maximum", validate=False, visible=False,
                           profile_dir=None, no_local_storage=True, runtime=False))
        call_kwargs = mock_loader.load.call_args[1]
        assert call_kwargs.get("inject_local_storage") is False

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_with_site_config(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        config_file = tmp_path / "site.json"
        config_file.write_text(json.dumps({"domains": ["github.com"]}))
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True, "site_name": "google",
            "cookies_injected": 5, "cookies_total": 5,
        }
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=str(config_file), fingerprint="default",
                           stealth_level="maximum", validate=False, visible=False,
                           profile_dir=None, no_local_storage=False, runtime=False))
        assert mock_loader.load.called

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_with_site_config_list(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        config_file = tmp_path / "sites.json"
        config_file.write_text(json.dumps([{"domains": ["github.com"]}]))
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True, "site_name": "google",
            "cookies_injected": 5, "cookies_total": 5,
        }
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=str(config_file), fingerprint="default",
                           stealth_level="maximum", validate=False, visible=False,
                           profile_dir=None, no_local_storage=False, runtime=False))
        assert mock_loader.load.called

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_with_site_config_empty_list(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        config_file = tmp_path / "sites.json"
        config_file.write_text(json.dumps([]))
        mock_loader = MagicMock()
        mock_loader.load.return_value = {
            "success": True, "site_name": "google",
            "cookies_injected": 5, "cookies_total": 5,
        }
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=str(config_file), fingerprint="default",
                           stealth_level="maximum", validate=False, visible=False,
                           profile_dir=None, no_local_storage=False, runtime=False))
        assert mock_loader.load.called

    @patch("tokenade.cli.session.SessionLoader")
    def test_load_failure_no_error_field(self, mock_loader_cls, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_loader = MagicMock()
        mock_loader.load.return_value = {"success": False}
        mock_loader_cls.return_value = mock_loader
        cmd_load(Namespace(file=str(f), site_config=None, fingerprint="default",
                           stealth_level="maximum", validate=False, visible=False,
                           profile_dir=None, no_local_storage=False, runtime=False))
        assert "failed" in capsys.readouterr().out.lower()


# ── cmd_transfer ─────────────────────────────────────────────────────────────

class TestCmdTransfer:
    def test_transfer_session_not_found(self, capsys):
        with pytest.raises(SystemExit) as ei:
            cmd_transfer(Namespace(session="/nonexistent/session.json", fingerprint="default",
                                   stealth_level="maximum", visible=False, profile_dir=None,
                                   validate_stealth=False))
        assert ei.value.code == 1
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.core.fingerprint.injector.validate_injection")
    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    def test_transfer_success(self, mock_bf_cls, mock_gh_cls, mock_fp_cls,
                              mock_validate, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_fp = MagicMock()
        mock_fp.load.return_value = None
        mock_fp_cls.return_value = mock_fp
        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.inject_session.return_value = True
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)
        cmd_transfer(Namespace(session=str(f), fingerprint=None, stealth_level="maximum",
                               visible=False, profile_dir=None, validate_stealth=False))
        assert "successful" in capsys.readouterr().out.lower()
        mock_browser.close.assert_called_once()

    @patch("tokenade.core.fingerprint.injector.validate_injection")
    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    def test_transfer_with_fingerprint(self, mock_bf_cls, mock_gh_cls, mock_fp_cls,
                                       mock_validate, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_fp = MagicMock()
        fp_obj = MagicMock()
        fp_obj.user_agent = "Mozilla/5.0 Chrome/120"
        fp_obj.screen_width = 1920
        fp_obj.screen_height = 1080
        fp_obj.platform = "Linux"
        fp_obj.to_dict.return_value = {"user_agent": "Mozilla/5.0 Chrome/120"}
        mock_fp.load.return_value = fp_obj
        mock_fp_cls.return_value = mock_fp
        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.inject_session.return_value = True
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)
        cmd_transfer(Namespace(session=str(f), fingerprint="my_fp", stealth_level="maximum",
                               visible=False, profile_dir=None, validate_stealth=False))
        output = capsys.readouterr().out
        assert "fingerprint" in output.lower() or "successful" in output.lower()

    @patch("tokenade.core.fingerprint.injector.validate_injection")
    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    def test_transfer_with_validate_stealth(self, mock_bf_cls, mock_gh_cls, mock_fp_cls,
                                            mock_validate, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_fp = MagicMock()
        fp_obj = MagicMock()
        fp_obj.user_agent = "Mozilla/5.0"
        fp_obj.screen_width = 1920
        fp_obj.screen_height = 1080
        fp_obj.platform = "Linux"
        fp_obj.to_dict.return_value = {}
        mock_fp.load.return_value = fp_obj
        mock_fp_cls.return_value = mock_fp
        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.inject_session.return_value = True
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)
        mock_validate.return_value = {
            "valid": True, "webdriver_undefined": True, "user_agent": "Mozilla/5.0"
        }
        cmd_transfer(Namespace(session=str(f), fingerprint="my_fp", stealth_level="maximum",
                               visible=False, profile_dir=None, validate_stealth=True))
        assert "stealth" in capsys.readouterr().out.lower()

    @patch("tokenade.core.fingerprint.injector.validate_injection")
    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    def test_transfer_inject_fails(self, mock_bf_cls, mock_gh_cls, mock_fp_cls,
                                   mock_validate, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_fp = MagicMock()
        mock_fp.load.return_value = None
        mock_fp_cls.return_value = mock_fp
        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.inject_session.return_value = False
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)
        with pytest.raises(SystemExit) as ei:
            cmd_transfer(Namespace(session=str(f), fingerprint=None, stealth_level="maximum",
                                   visible=False, profile_dir=None, validate_stealth=False))
        assert ei.value.code == 1
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.core.fingerprint.injector.validate_injection")
    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    def test_transfer_stealth_invalid(self, mock_bf_cls, mock_gh_cls, mock_fp_cls,
                                      mock_validate, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_fp = MagicMock()
        fp_obj = MagicMock()
        fp_obj.user_agent = "Mozilla/5.0"
        fp_obj.screen_width = 1920
        fp_obj.screen_height = 1080
        fp_obj.platform = "Linux"
        fp_obj.to_dict.return_value = {}
        mock_fp.load.return_value = fp_obj
        mock_fp_cls.return_value = mock_fp
        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.inject_session.return_value = True
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)
        mock_validate.return_value = {
            "valid": False, "webdriver_undefined": False, "user_agent": "Bot/1.0"
        }
        cmd_transfer(Namespace(session=str(f), fingerprint="my_fp", stealth_level="maximum",
                               visible=False, profile_dir=None, validate_stealth=True))
        output = capsys.readouterr().out
        assert "not be fully active" in output.lower() or "stealth" in output.lower()

    @patch("tokenade.core.fingerprint.injector.validate_injection")
    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    def test_transfer_with_profile_dir(self, mock_bf_cls, mock_gh_cls, mock_fp_cls,
                                       mock_validate, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_fp = MagicMock()
        mock_fp.load.return_value = None
        mock_fp_cls.return_value = mock_fp
        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.inject_session.return_value = True
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)
        profile_dir = str(tmp_path / "profile")
        cmd_transfer(Namespace(session=str(f), fingerprint=None, stealth_level="maximum",
                               visible=False, profile_dir=profile_dir, validate_stealth=False))
        assert "profile saved" in capsys.readouterr().out.lower()

    @patch("tokenade.core.fingerprint.injector.validate_injection")
    @patch("tokenade.core.fingerprint.manager.FingerprintManager")
    @patch("tokenade.cli.session.resolve_legacy_handler_class")
    @patch("tokenade.cli.session.BrowserFactory")
    def test_transfer_visible_mode(self, mock_bf_cls, mock_gh_cls, mock_fp_cls,
                                   mock_validate, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_fp = MagicMock()
        mock_fp.load.return_value = None
        mock_fp_cls.return_value = mock_fp
        mock_browser = MagicMock()
        mock_bf_cls.create.return_value = mock_browser
        mock_handler = MagicMock()
        mock_handler.inject_session.return_value = True
        mock_gh_cls.return_value = MagicMock(return_value=mock_handler)
        cmd_transfer(Namespace(session=str(f), fingerprint=None, stealth_level="maximum",
                               visible=True, profile_dir=None, validate_stealth=False))
        call_kwargs = mock_bf_cls.create.call_args[1]
        assert call_kwargs.get("headless") is False


# ── cmd_inject_profile ───────────────────────────────────────────────────────

class TestCmdInjectProfile:
    def test_inject_profile_not_found(self, capsys):
        cmd_inject_profile(Namespace(session="/nonexistent/session.tokenade", browser="chrome",
                                     profile="/tmp/profile", dry_run=False, no_backup=False))
        assert "not found" in capsys.readouterr().out.lower()

    def test_inject_profile_dry_run(self, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                     profile="/tmp/profile", dry_run=True, no_backup=False))
        output = capsys.readouterr().out
        assert "dry run" in output.lower() or "session info" in output.lower()

    def test_inject_profile_dry_run_with_cookies(self, tmp_path, capsys):
        cookies = [
            {"name": "sid", "value": "abc", "domain": ".google.com"},
            {"name": "token", "value": "xyz", "domain": ".google.com"},
            {"name": "session", "value": "123", "domain": ".google.com"},
        ]
        f = _make_session_file(tmp_path, "session", cookies=cookies)
        cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                     profile="/tmp/profile", dry_run=True, no_backup=False))
        output = capsys.readouterr().out
        assert "sample cookies" in output.lower() or "session info" in output.lower()

    def test_inject_profile_dry_run_many_cookies(self, tmp_path, capsys):
        cookies = [{"name": f"cookie{i}", "value": f"val{i}", "domain": ".google.com"}
                   for i in range(10)]
        f = _make_session_file(tmp_path, "session", cookies=cookies)
        cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                     profile="/tmp/profile", dry_run=True, no_backup=False))
        output = capsys.readouterr().out
        assert "more" in output.lower() or "sample cookies" in output.lower()

    @patch("tokenade.cli.session.inject_session_to_profile")
    def test_inject_profile_success(self, mock_inject, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.cookies_injected = 5
        mock_result.cookies_total = 5
        mock_result.backup_path = str(tmp_path / "backup")
        mock_inject.return_value = mock_result
        cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                     profile="/tmp/profile", dry_run=False, no_backup=False))
        assert "successful" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.inject_session_to_profile")
    def test_inject_profile_success_no_backup(self, mock_inject, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.cookies_injected = 3
        mock_result.cookies_total = 5
        mock_result.backup_path = None
        mock_inject.return_value = mock_result
        cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                     profile="/tmp/profile", dry_run=False, no_backup=True))
        call_kwargs = mock_inject.call_args[1]
        assert call_kwargs.get("backup") is False
        assert "successful" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.inject_session_to_profile")
    def test_inject_profile_failure(self, mock_inject, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Profile locked"
        mock_inject.return_value = mock_result
        with pytest.raises(SystemExit) as ei:
            cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                         profile="/tmp/profile", dry_run=False, no_backup=False))
        assert ei.value.code == 1
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.inject_session_to_profile")
    def test_inject_profile_exception(self, mock_inject, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_inject.side_effect = RuntimeError("db locked")
        with pytest.raises(SystemExit) as ei:
            cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                         profile="/tmp/profile", dry_run=False, no_backup=False))
        assert ei.value.code == 1
        assert "failed" in capsys.readouterr().out.lower()

    def test_inject_profile_dry_run_empty_cookies(self, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session", cookies=[])
        cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                     profile="/tmp/profile", dry_run=True, no_backup=False))
        output = capsys.readouterr().out
        assert "session info" in output.lower() or "cookies" in output.lower()

    @patch("tokenade.cli.session.inject_session_to_profile")
    def test_inject_profile_success_with_backup_path(self, mock_inject, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.cookies_injected = 5
        mock_result.cookies_total = 5
        mock_result.backup_path = "/backups/session.backup"
        mock_inject.return_value = mock_result
        cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                     profile="/tmp/profile", dry_run=False, no_backup=False))
        assert "backup" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.session.inject_session_to_profile")
    def test_inject_profile_failure_no_error(self, mock_inject, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session")
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = None
        mock_inject.return_value = mock_result
        with pytest.raises(SystemExit) as ei:
            cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                         profile="/tmp/profile", dry_run=False, no_backup=False))
        assert ei.value.code == 1
        assert "failed" in capsys.readouterr().out.lower()

    def test_inject_profile_dry_run_displays_auth_status(self, tmp_path, capsys):
        f = _make_session_file(tmp_path, "session", auth_status="logged_in")
        cmd_inject_profile(Namespace(session=str(f), browser="chrome",
                                     profile="/tmp/profile", dry_run=True, no_backup=False))
        output = capsys.readouterr().out
        assert "logged_in" in output.lower() or "session info" in output.lower()
