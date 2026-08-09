import importlib.metadata
import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from tokenade.core.integration.plugin_dependencies import check_runtime_dependencies


def test_runtime_dependency_marker_skips_other_platform():
    manifest = {
        "runtime_dependencies": {
            "python": ["missing-package>=1; sys_platform == 'never-this-platform'"]
        }
    }

    assert check_runtime_dependencies(manifest).ready


def test_runtime_dependency_reports_missing_distribution():
    manifest = {"runtime_dependencies": {"python": ["missing-package>=1"]}}

    with patch(
        "tokenade.core.integration.plugin_dependencies.importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        report = check_runtime_dependencies(manifest)

    assert not report.ready
    assert report.issues[0].kind == "python"
    assert report.issues[0].reason == "not installed"


def test_launch_stops_before_browser_when_required_plugin_missing(tmp_path, capsys):
    from tokenade.cli.handlers.browser_ops import cmd_launch

    session_path = tmp_path / "required.tokenade"
    session_path.write_text(json.dumps({
        "version": "3.0",
        "created_at": "2026-08-09T00:00:00Z",
        "site_name": "example",
        "auth_status": "logged_in",
        "cookies": [],
        "metadata": {
            "required_plugins": [{
                "name": "missing-handler",
                "min_version": "1.0.0",
                "required_at": "launch",
            }]
        },
    }))
    args = Namespace(
        browser="brave", session=str(session_path), url=None, port=9222,
        profile_dir=None, visible=True, headless=False, extra_args="",
        browser_path=None, proxy=None, proxy_file=None, proxy_rotate=False,
        proxy_strategy="health-weighted", humanize=False, geoip=False,
        no_cloak=False, profile=None, decrypt_password=None,
        plugin=None, no_plugin=False,
    )

    with patch("tokenade.core.integration.plugin_loader.PluginLoader.get_manifest", return_value=None), \
         patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as launcher:
        cmd_launch(args)

    launcher.assert_not_called()
    output = capsys.readouterr().out
    assert "Session requires unavailable plugins" in output
    assert "tokenade plugin install missing-handler" in output


def test_no_plugin_cannot_bypass_required_plugin(tmp_path, capsys):
    from tokenade.cli.handlers.browser_ops import cmd_launch

    session_path = tmp_path / "required.tokenade"
    session_path.write_text(json.dumps({
        "version": "3.0",
        "created_at": "2026-08-09T00:00:00Z",
        "site_name": "example",
        "auth_status": "logged_in",
        "cookies": [],
        "metadata": {"required_plugins": [{"name": "required-handler"}]},
    }))
    args = Namespace(
        browser="brave", session=str(session_path), url=None, port=9222,
        profile_dir=None, visible=True, headless=False, extra_args="",
        browser_path=None, proxy=None, proxy_file=None, proxy_rotate=False,
        proxy_strategy="health-weighted", humanize=False, geoip=False,
        no_cloak=False, profile=None, decrypt_password=None,
        plugin=None, no_plugin=True,
    )

    with patch("tokenade.core.browser.undetectable.SystemBrowserLauncher") as launcher:
        cmd_launch(args)

    launcher.assert_not_called()
    assert "Browser was not launched" in capsys.readouterr().out
