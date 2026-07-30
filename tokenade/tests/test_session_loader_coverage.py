"""Comprehensive tests for session_loader.py to boost coverage from 66% to 80%+."""

import json
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.importer.session_loader import SessionLoader


def _make_package(site_name="test", cookies=None, fingerprint=None,
                  local_storage=None, auth_status="logged_in"):
    return {
        "version": "2.0",
        "site_name": site_name,
        "auth_status": auth_status,
        "cookies": cookies or [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/"}],
        "fingerprint": fingerprint,
        "local_storage": local_storage or {},
    }


def _write_package(tmp_path, package, name="test.tokenade"):
    p = tmp_path / name
    p.write_text(json.dumps(package))
    return str(p)


class TestLoadFile:
    def test_success(self, tmp_path):
        path = _write_package(tmp_path, _make_package())
        loader = SessionLoader()
        result = loader.load_file(path)
        assert "cookies" in result
        assert result["site_name"] == "test"

    def test_file_not_found(self):
        loader = SessionLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_file("/nonexistent/file.tokenade")

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.tokenade"
        p.write_text("not json {{{")
        loader = SessionLoader()
        with pytest.raises(json.JSONDecodeError):
            loader.load_file(str(p))


class TestApplyFingerprint:
    def test_no_fingerprint(self):
        loader = SessionLoader()
        result = loader.apply_fingerprint(MagicMock(), fingerprint=None)
        assert result is True

    @patch("tokenade.core.importer.session_loader.inject_stealth_script", return_value=True)
    @patch("tokenade.core.importer.session_loader.BrowserFingerprint")
    def test_success(self, MockFP, mock_inject):
        fp_instance = MagicMock()
        MockFP.from_dict.return_value = fp_instance
        loader = SessionLoader()
        result = loader.apply_fingerprint(MagicMock(), fingerprint={"user_agent": "test"})
        assert result is True
        mock_inject.assert_called_once()

    @patch("tokenade.core.importer.session_loader.inject_stealth_script",
           side_effect=Exception("inject failed"))
    @patch("tokenade.core.importer.session_loader.BrowserFingerprint")
    def test_failure(self, MockFP, mock_inject):
        MockFP.from_dict.return_value = MagicMock()
        loader = SessionLoader()
        result = loader.apply_fingerprint(MagicMock(), fingerprint={"user_agent": "test"})
        assert result is False


class TestInjectCookies:
    def test_empty_cookies(self):
        loader = SessionLoader()
        result = loader.inject_cookies(MagicMock(), [])
        assert result == 0

    def test_invalid_cookie_missing_fields(self):
        loader = SessionLoader()
        bm = MagicMock()
        result = loader.inject_cookies(bm, [{"no_name": True}])
        assert result == 0

    def test_valid_cookie(self):
        loader = SessionLoader()
        bm = MagicMock()
        result = loader.inject_cookies(bm, [{"name": "c", "value": "v"}])
        assert result == 1
        bm.add_cookies.assert_called_once()

    def test_injection_failure(self):
        loader = SessionLoader()
        bm = MagicMock()
        bm.add_cookies.side_effect = Exception("add failed")
        result = loader.inject_cookies(bm, [{"name": "c", "value": "v"}])
        assert result == 0

    def test_multiple_cookies_partial_failure(self):
        loader = SessionLoader()
        bm = MagicMock()
        call_count = 0

        def side_effect(cookies):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("second failed")
        bm.add_cookies.side_effect = side_effect
        result = loader.inject_cookies(bm, [
            {"name": "c1", "value": "v1"},
            {"name": "c2", "value": "v2"},
        ])
        assert result == 1


class TestInjectLocalStorage:
    def test_empty_local_storage(self):
        loader = SessionLoader()
        result = loader.inject_local_storage(MagicMock(), {})
        assert result == 0

    def test_with_origin_navigation(self):
        loader = SessionLoader()
        bm = MagicMock()
        bm.evaluate.return_value = 2
        result = loader.inject_local_storage(bm, {"k1": "v1", "k2": "v2"},
                                             origin="https://example.com")
        assert result == 2
        bm.navigate.assert_called_once()

    def test_navigation_failure(self):
        loader = SessionLoader()
        bm = MagicMock()
        bm.navigate.side_effect = Exception("nav failed")
        bm.evaluate.return_value = 1
        result = loader.inject_local_storage(bm, {"k": "v"}, origin="https://x.com")
        assert result == 1

    def test_fallback_one_by_one(self):
        loader = SessionLoader()
        bm = MagicMock()
        bm.evaluate.return_value = "not_an_int"
        result = loader.inject_local_storage(bm, {"k1": "v1"})
        assert result == 1

    def test_fallback_one_by_one_failure(self):
        loader = SessionLoader()
        bm = MagicMock()
        # First call returns non-int (triggers fallback), second raises
        bm.evaluate.side_effect = ["not_an_int", Exception("eval failed")]
        result = loader.inject_local_storage(bm, {"k1": "v1", "k2": "v2"})
        assert result == 0

    def test_evaluate_exception(self):
        loader = SessionLoader()
        bm = MagicMock()
        bm.navigate.side_effect = None
        bm.evaluate.side_effect = Exception("eval failed")
        result = loader.inject_local_storage(bm, {"k": "v"})
        assert result == 0


class TestNormalizeCookie:
    def test_basic(self):
        loader = SessionLoader()
        result = loader._normalize_cookie({"name": "c", "value": "v"})
        assert result["name"] == "c"
        assert result["value"] == "v"
        assert result["path"] == "/"

    def test_firefox_millis_expiry(self):
        loader = SessionLoader()
        result = loader._normalize_cookie({"name": "c", "value": "v", "expires": 1700000000000})
        assert result["expires"] == 1700000000

    def test_seconds_expiry(self):
        loader = SessionLoader()
        result = loader._normalize_cookie({"name": "c", "value": "v", "expires": 1700000000})
        assert result["expires"] == 1700000000

    def test_session_cookie_no_expires(self):
        loader = SessionLoader()
        result = loader._normalize_cookie({"name": "c", "value": "v", "expires": 0})
        assert "expires" not in result

    def test_samesite_none_forces_secure(self):
        loader = SessionLoader()
        result = loader._normalize_cookie({"name": "c", "value": "v", "sameSite": "None"})
        assert result["secure"] is True

    def test_secure_and_httponly(self):
        loader = SessionLoader()
        result = loader._normalize_cookie({
            "name": "c", "value": "v", "secure": True, "httpOnly": True
        })
        assert result["secure"] is True
        assert result["httpOnly"] is True

    def test_samesite_lax(self):
        loader = SessionLoader()
        result = loader._normalize_cookie({"name": "c", "value": "v", "sameSite": "Lax"})
        assert result["sameSite"] == "Lax"

    def test_no_expires_field(self):
        loader = SessionLoader()
        result = loader._normalize_cookie({"name": "c", "value": "v"})
        assert "expires" not in result

    def test_empty_expires(self):
        loader = SessionLoader()
        result = loader._normalize_cookie({"name": "c", "value": "v", "expires": None})
        assert "expires" not in result


class TestValidateSession:
    @patch("tokenade.core.importer.session_loader.time")
    @patch("tokenade.core.importer.session_loader.SessionValidator")
    def test_with_validate_url(self, MockValidator, mock_time):
        mock_validator = MagicMock()
        mock_validator.validate.return_value = {"valid": True}
        MockValidator.return_value = mock_validator
        bm = MagicMock()
        loader = SessionLoader()
        result = loader.validate_session(bm, {
            "validate_url": "https://example.com",
            "wait_seconds": 2,
        })
        bm.navigate.assert_called_once_with("https://example.com",
                                            wait_until="domcontentloaded",
                                            timeout=30000)
        assert result["valid"] is True

    @patch("tokenade.core.importer.session_loader.time")
    @patch("tokenade.core.importer.session_loader.SessionValidator")
    def test_navigation_failure(self, MockValidator, mock_time):
        mock_validator = MagicMock()
        mock_validator.validate.return_value = {"valid": False}
        MockValidator.return_value = mock_validator
        bm = MagicMock()
        bm.navigate.side_effect = Exception("nav failed")
        loader = SessionLoader()
        result = loader.validate_session(bm, {
            "validate_url": "https://example.com",
            "wait_seconds": 0,
        })
        assert result["valid"] is False

    @patch("tokenade.core.importer.session_loader.SessionValidator")
    def test_no_validate_url(self, MockValidator):
        mock_validator = MagicMock()
        mock_validator.validate.return_value = {"valid": True}
        MockValidator.return_value = mock_validator
        bm = MagicMock()
        loader = SessionLoader()
        loader.validate_session(bm, {"wait_seconds": 0})
        bm.navigate.assert_not_called()


class TestInferOrigin:
    def test_from_site_config_domains(self):
        loader = SessionLoader()
        result = loader._infer_origin({}, {"domains": ["example.com"]})
        assert result == "https://example.com"

    def test_from_site_config_dotted_domain(self):
        loader = SessionLoader()
        result = loader._infer_origin({}, {"domains": [".example.com"]})
        assert result is None

    def test_from_cookie_domain(self):
        loader = SessionLoader()
        result = loader._infer_origin({
            "cookies": [{"domain": "test.org"}]
        })
        assert result == "https://test.org"

    def test_from_cookie_http_domain(self):
        loader = SessionLoader()
        result = loader._infer_origin({
            "cookies": [{"domain": "http://test.org"}]
        })
        assert result == "http://test.org"

    def test_from_site_name(self):
        loader = SessionLoader()
        result = loader._infer_origin({"site_name": "mysite"})
        assert result == "https://mysite.com"

    def test_unknown_site_name(self):
        loader = SessionLoader()
        result = loader._infer_origin({"site_name": "unknown"})
        assert result is None

    def test_no_data(self):
        loader = SessionLoader()
        result = loader._infer_origin({})
        assert result is None

    def test_empty_domains(self):
        loader = SessionLoader()
        result = loader._infer_origin({}, {"domains": []})
        assert result is None


class TestBuildDefaultSiteConfig:
    @patch("tokenade.core.importer.site_configs.get_site_config")
    def test_preset_found(self, mock_get):
        mock_get.return_value = {"name": "GitHub", "domains": ["github.com"]}
        loader = SessionLoader()
        result = loader._build_default_site_config({"site_name": "github"})
        assert result["name"] == "GitHub"

    @patch("tokenade.core.importer.site_configs.get_site_config", return_value={})
    def test_no_preset_with_auth_cookies(self, _mock):
        loader = SessionLoader()
        result = loader._build_default_site_config({
            "site_name": "custom",
            "cookies": [
                {"domain": "custom.com", "name": "session_id"},
                {"domain": "custom.com", "name": "token_val"},
                {"domain": "custom.com", "name": "auth_cookie"},
                {"domain": "custom.com", "name": "sid"},
                {"domain": "custom.com", "name": "csrf_token"},
                {"domain": "custom.com", "name": "regular_cookie"},
            ],
        })
        assert "custom.com" in result["domains"]
        assert len(result["critical_cookies"]) <= 5
        assert "session_id" in result["critical_cookies"]
        assert "token_val" in result["critical_cookies"]

    @patch("tokenade.core.importer.site_configs.get_site_config", return_value={})
    def test_no_preset_no_auth_cookies(self, _mock):
        loader = SessionLoader()
        result = loader._build_default_site_config({
            "site_name": "myapp",
            "cookies": [{"domain": "myapp.com", "name": "theme"}],
        })
        assert result["critical_cookies"] == []


class TestLoadWorkflow:
    def test_file_not_found(self):
        loader = SessionLoader()
        result = loader.load("/nonexistent/file.tokenade", validate=False)
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.tokenade"
        p.write_text("not json {{{")
        loader = SessionLoader()
        result = loader.load(str(p), validate=False)
        assert result["success"] is False
        assert "invalid" in result["error"].lower() or "expecting" in result["error"].lower()

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_browser_launch_error(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        MockFactory.create.return_value.launch.side_effect = Exception("browser launch failed")
        loader = SessionLoader()
        result = loader.load(path, validate=False)
        assert result["success"] is False

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_successful_load_no_validate(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        result = loader.load(path, validate=False)
        assert result["success"] is True
        assert result["cookies_injected"] == 1

    @patch("tokenade.core.importer.session_loader.time")
    @patch("tokenade.core.importer.session_loader.SessionValidator")
    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_successful_load_with_validate(self, MockFactory, MockValidator, mock_time, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        mock_validator = MagicMock()
        mock_validator.validate.return_value = {"valid": True}
        MockValidator.return_value = mock_validator
        loader = SessionLoader()
        result = loader.load(path, validate=True, site_config={"validate_url": None})
        assert result["success"] is True

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_with_target_fingerprint(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        fp_manager = MagicMock()
        fp_mock = MagicMock()
        fp_mock.to_dict.return_value = {"user_agent": "test"}
        fp_manager.load.return_value = fp_mock
        loader = SessionLoader(fp_manager=fp_manager)
        result = loader.load(path, target_fp_name="test_fp", validate=False)
        assert result["success"] is True

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_target_fingerprint_not_found(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        fp_manager = MagicMock()
        fp_manager.load.return_value = None
        loader = SessionLoader(fp_manager=fp_manager)
        result = loader.load(path, target_fp_name="nonexistent", validate=False)
        assert result["success"] is True

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_with_source_fingerprint(self, MockFactory, tmp_path):
        fp = {"user_agent": "test_ua", "platform": "Linux"}
        path = _write_package(tmp_path, _make_package(fingerprint=fp))
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        with patch.object(loader, "apply_fingerprint", return_value=True) as mock_apply:
            result = loader.load(path, validate=False)
            assert result["success"] is True
            mock_apply.assert_called_once()

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_with_local_storage(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package(
            local_storage={"k1": "v1"}
        ))
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        with patch.object(loader, "inject_local_storage", return_value=1):
            result = loader.load(path, validate=False)
            assert result["local_storage_injected"] == 1

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_with_v3_storage_local_by_origin(self, MockFactory, tmp_path):
        package = _make_package()
        package.pop("local_storage", None)
        package["storage"] = {"local": {"https://api.hcnsec.cn": {"token": "v1", "user": "v2"}}}
        path = _write_package(tmp_path, package)
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        with patch.object(loader, "inject_local_storage", return_value=2) as mock_ls:
            result = loader.load(path, validate=False)
            assert result["local_storage_total"] == 2
            assert result["local_storage_injected"] == 2
            mock_ls.assert_called_once_with(mock_bm, {"token": "v1", "user": "v2"}, origin="https://api.hcnsec.cn")

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_local_storage_disabled(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package(
            local_storage={"k1": "v1"}
        ))
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        with patch.object(loader, "inject_local_storage", return_value=0) as mock_ls:
            loader.load(path, validate=False, inject_local_storage=False)
            mock_ls.assert_not_called()

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_with_profile_dir(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        result = loader.load(path, validate=False, profile_dir="/tmp/profile")
        assert result["success"] is True

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_browser_close_on_error(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        mock_bm.add_cookies.side_effect = Exception("cookie inject failed")
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        result = loader.load(path, validate=False)
        assert result["success"] is False

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_browser_close_exception_ignored(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        mock_bm.add_cookies.side_effect = Exception("cookie inject failed")
        mock_bm.close.side_effect = Exception("close failed")
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        result = loader.load(path, validate=False)
        assert result["success"] is False
        # close() failed, so _browser is NOT set to None (the exception is caught)
        assert loader._browser is not None

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_validate_builds_default_config(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        with patch("tokenade.core.importer.session_loader.SessionValidator") as MockVal, \
                patch("tokenade.core.importer.session_loader.time"):
            mock_v = MagicMock()
            mock_v.validate.return_value = {"valid": True}
            MockVal.return_value = mock_v
            result = loader.load(path, validate=True)
            assert result["success"] is True

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_permission_denied_hint(self, MockFactory, tmp_path):
        loader = SessionLoader()
        with patch("builtins.open", side_effect=PermissionError("denied")):
            result = loader.load("/some/file.tokenade", validate=False)
            assert result["success"] is False

    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_success_with_local_storage_and_no_inject(self, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package(local_storage={"k1": "v1"}))
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        loader = SessionLoader()
        result = loader.load(path, validate=False, inject_local_storage=False)
        assert result["local_storage_injected"] == 0


class TestLoadIntoRuntime:
    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_session_load_failed(self, MockFactory, tmp_path):
        mock_bm = MagicMock()
        mock_bm.add_cookies.side_effect = Exception("fail")
        MockFactory.create.return_value = mock_bm
        path = _write_package(tmp_path, _make_package())
        loader = SessionLoader()
        result = loader.load_into_runtime(path)
        assert result["success"] is False
        assert result.get("runtime_loaded") is not True

    @patch("tokenade.core.importer.session_loader.time")
    @patch("tokenade.core.importer.session_loader.SessionValidator")
    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_no_runtime_engine(self, MockFactory, MockValidator, mock_time, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        mock_v = MagicMock()
        mock_v.validate.return_value = {"valid": True}
        MockValidator.return_value = mock_v
        loader = SessionLoader()
        result = loader.load_into_runtime(path, runtime_engine=None)
        assert result.get("runtime_loaded") is False
        assert result.get("runtime_error") == "No RuntimeEngine provided"

    @patch("tokenade.core.importer.session_loader.time")
    @patch("tokenade.core.importer.session_loader.SessionValidator")
    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_with_runtime_engine(self, mock_time, MockValidator, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        mock_v = MagicMock()
        mock_v.validate.return_value = {"valid": True}
        MockValidator.return_value = mock_v
        mock_runtime = MagicMock()
        loader = SessionLoader()
        result = loader.load_into_runtime(path, runtime_engine=mock_runtime)
        assert result.get("runtime_loaded") is True

    @patch("tokenade.core.importer.session_loader.time")
    @patch("tokenade.core.importer.session_loader.SessionValidator")
    @patch("tokenade.core.importer.session_loader.BrowserFactory")
    def test_runtime_engine_exception(self, mock_time, MockValidator, MockFactory, tmp_path):
        path = _write_package(tmp_path, _make_package())
        mock_bm = MagicMock()
        MockFactory.create.return_value = mock_bm
        mock_v = MagicMock()
        mock_v.validate.return_value = {"valid": True}
        MockValidator.return_value = mock_v
        # Pass a string that triggers an error in SessionData creation
        mock_runtime = MagicMock()
        loader = SessionLoader()
        # Mock load_file to return package with bad auth_status to trigger error
        with patch.object(loader, "load_file", return_value={
            "site_name": "test",
            "auth_status": "invalid_status",
            "cookies": [],
            "tokens": [],
        }):
            result = loader.load_into_runtime(path, runtime_engine=mock_runtime)
            assert result.get("runtime_loaded") is False


class TestCloseAndGetLastResult:
    def test_close_no_browser(self):
        loader = SessionLoader()
        loader.close()

    def test_close_with_browser(self):
        loader = SessionLoader()
        mock_bm = MagicMock()
        loader._browser = mock_bm
        loader.close()
        mock_bm.close.assert_called_once()
        assert loader._browser is None

    def test_close_exception_ignored(self):
        loader = SessionLoader()
        mock_bm = MagicMock()
        mock_bm.close.side_effect = Exception("close err")
        loader._browser = mock_bm
        loader.close()
        # Exception caught, but _browser NOT set to None because the code only
        # sets _browser = None after successful close()
        assert loader._browser is mock_bm

    def test_get_last_result_initial(self):
        loader = SessionLoader()
        assert loader.get_last_result() is None

    def test_get_last_result_after_load(self, tmp_path):
        path = _write_package(tmp_path, _make_package())
        loader = SessionLoader()
        result = loader.load(path, validate=False)
        assert loader.get_last_result() is result

    def test_site_name_in_result(self, tmp_path):
        path = _write_package(tmp_path, _make_package(site_name="mysite"))
        loader = SessionLoader()
        with patch("tokenade.core.importer.session_loader.BrowserFactory") as MockFactory:
            MockFactory.create.return_value = MagicMock()
            result = loader.load(path, validate=False)
            assert result.get("site_name") == "mysite"

    def test_embedded_site_handler_metadata_in_result(self, tmp_path):
        package = _make_package(site_name="discord")
        package["metadata"] = {
            "site_handler": {
                "plugin_name": "discord-handler",
                "export_domains": ["discord.com"],
                "storage_origins": ["https://discord.com"],
            }
        }
        path = _write_package(tmp_path, package)
        loader = SessionLoader()
        with patch("tokenade.core.importer.session_loader.BrowserFactory") as MockFactory:
            MockFactory.create.return_value = MagicMock()
            result = loader.load(path, validate=False)
            assert result["site_handler"]["plugin_name"] == "discord-handler"

    @patch("tokenade.core.importer.site_configs.get_site_config", return_value=None)
    def test_embedded_site_handler_domains_used_for_default_site_config(self, _mock_get_site_config):
        package = _make_package(site_name="discord")
        package["metadata"] = {
            "site_handler": {
                "plugin_name": "discord-handler",
                "export_domains": ["discord.com", "discordapp.com"],
            }
        }
        loader = SessionLoader()
        site_config = loader._build_default_site_config(package)
        assert site_config["domains"] == ["discord.com", "discordapp.com"]

    def test_embedded_storage_origin_used_for_infer_origin(self):
        package = _make_package(site_name="discord")
        package["metadata"] = {
            "site_handler": {
                "plugin_name": "discord-handler",
                "storage_origins": ["https://discord.com"],
            }
        }
        loader = SessionLoader()
        assert loader._infer_origin(package) == "https://discord.com"
