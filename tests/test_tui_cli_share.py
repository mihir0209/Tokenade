"""Tests for TUI CLI runner + KISS share full-URL retrieve."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tokenade.tui.cli_runner import (
    tokenade_argv,
    cmd_launch,
    cmd_load,
    cmd_health,
    cmd_refresh_browser,
    cmd_export,
    format_receive_help,
    run_tokenade,
)
from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig


class TestCliRunner:
    def test_tokenade_argv(self):
        argv = tokenade_argv("launch", "-s", "x.tokenade")
        assert "-m" in argv
        assert "tokenade" in argv
        assert argv[-3:] == ["launch", "-s", "x.tokenade"]

    def test_cmd_builders(self):
        assert cmd_health("/a.tokenade") == ["health", "-s", "/a.tokenade"]
        launch = cmd_launch("/a.tokenade", browser="firefox", url="https://x.com")
        assert launch[:2] == ["launch", "-s"]
        assert "-b" in launch and "firefox" in launch
        assert "-u" in launch
        assert "--visible" in launch
        load = cmd_load("/a.tokenade", visible=True)
        assert load[0] == "load" and "--file" in load
        ref = cmd_refresh_browser("/a.tokenade", browser="cloak")
        assert ref[0] == "refresh-browser"
        assert "--headless" in ref

    def test_cmd_export(self):
        assert cmd_export(list_profiles=True) == ["export", "--list-profiles"]
        assert cmd_export(list_handlers=True) == ["export", "--list-handlers"]
        args = cmd_export(
            browser_name="firefox",
            profile="default",
            domains="google.com",
            output="/tmp/x.tokenade",
            full=True,
            encrypt_password="secret",
            collect_fingerprint=True,
        )
        assert args[0] == "export"
        assert "--browser-name" in args and "firefox" in args
        assert "--profile" in args and "default" in args
        assert "--domains" in args and "google.com" in args
        assert "--output" in args and "/tmp/x.tokenade" in args
        assert "--full" in args
        assert "--encrypt-password" in args
        assert "--collect-fingerprint" in args
        bare = cmd_export(browser_name="chrome", full=False, no_plugin=True)
        assert "--full" not in bare
        assert "--no-plugin" in bare
        with_proxy = cmd_export(
            browser_name="vivaldi", profile="Default", proxy_plugin="proxy-rotate"
        )
        assert "vivaldi" in with_proxy
        assert "--proxy-plugin" in with_proxy and "proxy-rotate" in with_proxy

    def test_format_receive_help(self):
        text = format_receive_help(
            short_id="abc123",
            full_url="tokenade://share/abc123?data=xxx",
        )
        assert "share-url retrieve abc123" in text
        assert "tokenade:// is CLI-only" in text
        assert "not a browser protocol" in text
        assert "load --file" in text

    def test_run_tokenade_health_smoke(self, tmp_path):
        # Just ensure subprocess path works for --help
        result = run_tokenade(["--help"], timeout=30)
        assert result.returncode == 0
        assert "export" in result.stdout.lower() or "Tokenade" in result.stdout


class TestShareFullUrl:
    def test_create_returns_full_url(self, tmp_path):
        sess = tmp_path / "s.tokenade"
        sess.write_text(json.dumps({"cookies": [], "site_name": "ex.com"}))
        r = SessionURLShortener(URLShortenerConfig()).create_share(
            str(sess), password="password123",
        )
        assert r["success"]
        assert r["full_url"].startswith("tokenade://share/")
        assert "?data=" in r["full_url"]
        assert r["short_id"] in r["full_url"]
        assert r["short_url"] == f"tokenade://share/{r['short_id']}"

    def test_retrieve_from_full_url_without_store(self, tmp_path, monkeypatch):
        """Peer machine: only full URL + password — no shortened_urls.json entry."""
        sess = tmp_path / "s.tokenade"
        sess.write_text(json.dumps({
            "cookies": [{"name": "a", "value": "1"}],
            "site_name": "ex.com",
        }))
        creator = SessionURLShortener(URLShortenerConfig())
        created = creator.create_share(str(sess), password="password123")
        full = created["full_url"]

        # Fresh shortener with empty store
        empty_store = tmp_path / "empty_urls.json"
        empty_store.write_text("{}")
        receiver = SessionURLShortener(URLShortenerConfig())
        receiver._url_store = empty_store
        receiver._urls = {}

        out = tmp_path / "got.tokenade"
        result = receiver.retrieve_session(full, "password123", output_path=str(out))
        assert result["success"], result
        assert result.get("source") == "embedded"
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["site_name"] == "ex.com"

    def test_retrieve_wrong_password(self, tmp_path):
        sess = tmp_path / "s.tokenade"
        sess.write_text(json.dumps({"cookies": []}))
        created = SessionURLShortener(URLShortenerConfig()).create_share(
            str(sess), password="password123",
        )
        r = SessionURLShortener(URLShortenerConfig()).retrieve_session(
            created["full_url"], "wrongpass", write_file=False,
        )
        assert not r["success"]

    def test_create_embeds_file_name_and_default_output(self, tmp_path):
        sess = tmp_path / "my-google.tokenade"
        sess.write_text(json.dumps({
            "cookies": [{"name": "a", "value": "1"}],
            "site_name": "google.com",
            "metadata": {"cookie_count": 1},
        }))
        created = SessionURLShortener(URLShortenerConfig()).create_share(
            str(sess), password="password123",
        )
        assert created.get("file_name") == "my-google.tokenade"

        out_dir = tmp_path / "inbox"
        out_dir.mkdir()
        # Existing name → suffix -2
        (out_dir / "my-google.tokenade").write_text("{}")
        r = SessionURLShortener(URLShortenerConfig()).retrieve_session(
            created["full_url"],
            "password123",
            default_dir=str(out_dir),
        )
        assert r["success"], r
        assert r["file_name"] == "my-google.tokenade"
        saved = Path(r["output_path"])
        assert saved.parent == out_dir
        assert saved.name == "my-google-2.tokenade"
        data = json.loads(saved.read_text())
        assert data["metadata"]["file_name"] == "my-google.tokenade"
        assert data["site_name"] == "google.com"
