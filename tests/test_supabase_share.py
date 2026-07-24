"""Supabase share store + config resolution."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tokenade.core.sharing.supabase_store import (
    PUBLIC_SUPABASE_ANON_KEY,
    PUBLIC_SUPABASE_URL,
    SupabaseConfig,
    SupabaseShareStore,
)


class TestSupabaseConfig:
    def test_public_default_when_empty(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TOKENADE_SUPABASE_URL", raising=False)
        monkeypatch.delenv("TOKENADE_SUPABASE_ANON_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text("{}")
        with patch("tokenade.core.config.DEFAULT_CONFIG_FILE", cfg_path):
            with patch("tokenade.core.config.load_config") as lc:
                from tokenade.core.config import TokenadeConfig
                lc.return_value = TokenadeConfig(str(cfg_path))
                c = SupabaseConfig.from_env()
        assert c.enabled
        assert c.source == "public"
        assert c.is_public_default
        assert c.url == PUBLIC_SUPABASE_URL
        assert c.anon_key == PUBLIC_SUPABASE_ANON_KEY

    def test_opt_out_default(self, monkeypatch):
        monkeypatch.delenv("TOKENADE_SUPABASE_URL", raising=False)
        monkeypatch.delenv("TOKENADE_SUPABASE_ANON_KEY", raising=False)
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
        with patch("tokenade.core.config.load_config") as lc:
            cfg = MagicMock()
            cfg.get.side_effect = lambda k, d=None: {
                "supabase_url": None,
                "supabase_anon_key": None,
                "supabase_use_default": False,
                "supabase_table": "tokenade_shares",
            }.get(k, d)
            lc.return_value = cfg
            c = SupabaseConfig.from_env()
        assert not c.enabled
        assert c.source == "none"

    def test_cli_override(self):
        c = SupabaseConfig.from_env(
            url="https://mine.supabase.co",
            anon_key="sb_publishable_x",
        )
        assert c.source == "override"
        assert c.url == "https://mine.supabase.co"
        assert not c.is_public_default


class TestSupabaseShareStoreRPC:
    def test_put_calls_rpc(self):
        store = SupabaseShareStore(
            SupabaseConfig(
                url="https://example.supabase.co",
                anon_key="k",
                source="override",
            )
        )
        with patch.object(store, "_rpc", return_value={"success": True, "short_id": "abc"}) as rpc:
            r = store.put_share("abcdefghij", "ciphertext_payload_xx", max_uses=2)
        assert r["success"]
        assert rpc.call_args[0][0] == "tokenade_put_share"
        body = rpc.call_args[0][1]
        assert body["p_short_id"] == "abcdefghij"
        assert "password" not in json.dumps(body).lower()

    def test_get_consumes_via_rpc(self):
        store = SupabaseShareStore(
            SupabaseConfig(url="https://example.supabase.co", anon_key="k")
        )
        with patch.object(
            store,
            "_rpc",
            return_value={
                "short_id": "abcdefghij",
                "ciphertext": "ct",
                "max_uses": 3,
                "current_uses": 1,
                "remaining_uses": 2,
            },
        ) as rpc:
            row = store.get_share("abcdefghij")
        assert row["ciphertext"] == "ct"
        assert rpc.call_args[0][0] == "tokenade_get_share"
