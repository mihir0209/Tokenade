"""Supabase-backed remote share store.

Stores only password-encrypted payloads. The password is never uploaded.
All access goes through SECURITY DEFINER RPCs (no direct table SELECT).

Public defaults (baked OSS project) work out of the box. Users who want
full privacy can override with their own Supabase project via:

  env TOKENADE_SUPABASE_URL / TOKENADE_SUPABASE_ANON_KEY
  env SUPABASE_URL / SUPABASE_ANON_KEY
  ~/.tokenade/config.json:
      supabase_url, supabase_anon_key
      supabase_use_default: false   # force off remote
  CLI: share-url create --supabase-url ... --supabase-key ...

Limits (enforced server-side on the public project):
  - 30 creates / IP / hour
  - max expiry 7 days (default 24h)
  - max_uses capped 1–50 (0 becomes 10 on public store)
  - ciphertext max 2_000_000 chars (~1.5 MB session before encrypt)
  - no list/dump of shares (RPC by short_id only)

SQL (run once as postgres on a private project) — see
``tokenade_schema_sql()`` or docs.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Must match tokenade_put_share SQL length check
MAX_CIPHERTEXT_CHARS = 2_000_000
# Skip embedding full payload in local shortened_urls.json above this size
MAX_EMBEDDED_URL_CHARS = 200_000

# Baked public Tokenade share project (ciphertext only; publishable key).
# Never put the database password or service_role key here.
PUBLIC_SUPABASE_URL = "https://guruxdtvwrahuvvxqgcr.supabase.co"
PUBLIC_SUPABASE_ANON_KEY = "sb_publishable_t1khpj4iw9P_Hy_fEV7Wqw_lnJXBiIy"


def tokenade_schema_sql() -> str:
    """Return hardened SQL for a private Supabase project (paste in SQL editor)."""
    return """
-- Tokenade private share store (RPC-only; no open table access)
create table if not exists public.tokenade_shares (
  short_id text primary key,
  ciphertext text not null,
  expires_at timestamptz,
  max_uses int not null default 0,
  current_uses int not null default 0,
  revoked boolean not null default false,
  created_at timestamptz not null default now(),
  creator_ip text,
  last_access_ip text
);
create index if not exists tokenade_shares_created_at_idx
  on public.tokenade_shares (created_at desc);
alter table public.tokenade_shares enable row level security;
revoke all on public.tokenade_shares from anon, authenticated;
grant usage on schema public to anon, authenticated;

create table if not exists public.tokenade_share_rate (
  ip text not null,
  window_start timestamptz not null default date_trunc('hour', now()),
  create_count int not null default 0,
  primary key (ip, window_start)
);
alter table public.tokenade_share_rate enable row level security;
revoke all on public.tokenade_share_rate from anon, authenticated;

create or replace function public._tokenade_client_ip()
returns text language sql stable as $$
  select coalesce(
    nullif(current_setting('request.headers', true)::json->>'x-forwarded-for', ''),
    nullif(current_setting('request.headers', true)::json->>'cf-connecting-ip', ''),
    nullif(current_setting('request.headers', true)::json->>'x-real-ip', ''),
    'unknown'
  );
$$;

create or replace function public.tokenade_put_share(
  p_short_id text, p_ciphertext text,
  p_expires_at timestamptz default null, p_max_uses int default 0
) returns json language plpgsql security definer set search_path = public as $$
declare
  v_ip text := trim(split_part(public._tokenade_client_ip(), ',', 1));
  v_count int; v_max_per_hour int := 30; v_max_uses int := greatest(coalesce(p_max_uses, 0), 0);
begin
  if p_short_id is null or length(p_short_id) < 8 or length(p_short_id) > 64 then
    raise exception 'invalid short_id' using errcode = '22023';
  end if;
  if p_ciphertext is null or length(p_ciphertext) < 16 then
    raise exception 'invalid ciphertext' using errcode = '22023';
  end if;
  if length(p_ciphertext) > 2000000 then
    raise exception 'ciphertext too large (max 2000000 chars)' using errcode = '22023';
  end if;
  if p_expires_at is not null and p_expires_at > now() + interval '7 days' then
    p_expires_at := now() + interval '7 days';
  end if;
  if p_expires_at is null then p_expires_at := now() + interval '24 hours'; end if;
  if v_max_uses = 0 then v_max_uses := 10;
  elsif v_max_uses > 50 then v_max_uses := 50; end if;

  insert into public.tokenade_share_rate (ip, window_start, create_count)
  values (v_ip, date_trunc('hour', now()), 1)
  on conflict (ip, window_start) do update
    set create_count = public.tokenade_share_rate.create_count + 1
  returning create_count into v_count;
  if v_count > v_max_per_hour then
    raise exception 'rate limit exceeded' using errcode = '54000';
  end if;

  insert into public.tokenade_shares (
    short_id, ciphertext, expires_at, max_uses, current_uses, revoked, creator_ip
  ) values (p_short_id, p_ciphertext, p_expires_at, v_max_uses, 0, false, v_ip);

  return json_build_object(
    'success', true, 'short_id', p_short_id,
    'expires_at', p_expires_at, 'max_uses', v_max_uses
  );
end;
$$;

create or replace function public.tokenade_get_share(p_short_id text)
returns json language plpgsql security definer set search_path = public as $$
declare r public.tokenade_shares%rowtype;
  v_ip text := trim(split_part(public._tokenade_client_ip(), ',', 1));
begin
  if p_short_id is null or length(p_short_id) < 8 then return null; end if;
  select * into r from public.tokenade_shares where short_id = p_short_id;
  if not found then return null; end if;
  if r.revoked then return json_build_object('error', 'revoked'); end if;
  if r.expires_at is not null and r.expires_at < now() then
    return json_build_object('error', 'expired');
  end if;
  if r.max_uses > 0 and r.current_uses >= r.max_uses then
    return json_build_object('error', 'max_uses');
  end if;
  update public.tokenade_shares
     set current_uses = current_uses + 1, last_access_ip = v_ip
   where short_id = p_short_id and revoked = false
     and (expires_at is null or expires_at >= now())
     and (max_uses = 0 or current_uses < max_uses)
  returning * into r;
  if not found then return json_build_object('error', 'unavailable'); end if;
  return json_build_object(
    'short_id', r.short_id, 'ciphertext', r.ciphertext,
    'expires_at', r.expires_at, 'max_uses', r.max_uses,
    'current_uses', r.current_uses,
    'remaining_uses', case when r.max_uses > 0 then r.max_uses - r.current_uses else null end
  );
end;
$$;

create or replace function public.tokenade_peek_share(p_short_id text)
returns json language plpgsql security definer set search_path = public as $$
declare r record;
begin
  select short_id, expires_at, max_uses, current_uses, revoked, created_at
    into r from public.tokenade_shares where short_id = p_short_id;
  if not found then return null; end if;
  return json_build_object(
    'short_id', r.short_id, 'expires_at', r.expires_at,
    'max_uses', r.max_uses, 'current_uses', r.current_uses,
    'revoked', r.revoked, 'created_at', r.created_at, 'has_ciphertext', true
  );
end;
$$;

create or replace function public.tokenade_revoke_share(p_short_id text)
returns json language plpgsql security definer set search_path = public as $$
begin
  update public.tokenade_shares set revoked = true where short_id = p_short_id;
  if found then return json_build_object('success', true); end if;
  return json_build_object('success', false, 'error', 'not_found');
end;
$$;

grant execute on function public.tokenade_put_share(text, text, timestamptz, int) to anon, authenticated;
grant execute on function public.tokenade_get_share(text) to anon, authenticated;
grant execute on function public.tokenade_peek_share(text) to anon, authenticated;
grant execute on function public.tokenade_revoke_share(text) to anon, authenticated;
""".strip()


@dataclass
class SupabaseConfig:
    url: str
    anon_key: str
    table: str = "tokenade_shares"
    source: str = "none"  # env | config | public | override | none

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.anon_key)

    @property
    def is_public_default(self) -> bool:
        return (
            self.enabled
            and self.url.rstrip("/") == PUBLIC_SUPABASE_URL.rstrip("/")
        )

    @classmethod
    def from_env(
        cls,
        *,
        url: Optional[str] = None,
        anon_key: Optional[str] = None,
        use_default: Optional[bool] = None,
    ) -> "SupabaseConfig":
        """Resolve config with precedence:

        1. Explicit url/anon_key args (CLI override)
        2. TOKENADE_SUPABASE_* / SUPABASE_* env
        3. ~/.tokenade/config.json (private project)
        4. Baked public defaults (unless supabase_use_default is false)
        """
        table = os.environ.get("TOKENADE_SUPABASE_TABLE") or "tokenade_shares"
        source = "none"

        if url and anon_key:
            return cls(
                url=url.rstrip("/"),
                anon_key=anon_key,
                table=table,
                source="override",
            )

        env_url = (
            os.environ.get("TOKENADE_SUPABASE_URL")
            or os.environ.get("SUPABASE_URL")
            or ""
        ).rstrip("/")
        env_key = (
            os.environ.get("TOKENADE_SUPABASE_ANON_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or ""
        )
        if env_url and env_key:
            return cls(url=env_url, anon_key=env_key, table=table, source="env")

        cfg_url = cfg_key = ""
        cfg_use_default: Optional[bool] = None
        try:
            from tokenade.core.config import load_config

            cfg = load_config()
            cfg_url = str(cfg.get("supabase_url") or "").rstrip("/")
            cfg_key = str(cfg.get("supabase_anon_key") or "")
            raw_ud = cfg.get("supabase_use_default")
            if raw_ud is not None:
                cfg_use_default = bool(raw_ud)
            t = cfg.get("supabase_table")
            if t:
                table = str(t)
        except Exception:
            pass

        if use_default is not None:
            cfg_use_default = use_default

        if cfg_url and cfg_key:
            return cls(url=cfg_url, anon_key=cfg_key, table=table, source="config")

        # Explicit opt-out of public default
        if cfg_use_default is False:
            return cls(url="", anon_key="", table=table, source="none")

        # Baked public project
        return cls(
            url=PUBLIC_SUPABASE_URL,
            anon_key=PUBLIC_SUPABASE_ANON_KEY,
            table=table,
            source="public",
        )


class SupabaseShareStore:
    """Minimal REST client — RPC only (no direct table access)."""

    def __init__(self, config: Optional[SupabaseConfig] = None):
        self.config = config or SupabaseConfig.from_env()

    @property
    def available(self) -> bool:
        return self.config.enabled

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.config.anon_key,
            "Authorization": f"Bearer {self.config.anon_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _rpc(self, fn: str, body: dict, *, timeout: float = 20) -> Any:
        url = f"{self.config.url}/rest/v1/rpc/{fn}"
        data = json.dumps(body).encode()
        # Scale timeout with body size (large near-limit uploads on slow links)
        timeout = max(float(timeout), 15.0 + len(data) / 200_000.0)
        req = urllib.request.Request(
            url, data=data, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace") if e.fp else ""
            raise RuntimeError(f"Supabase HTTP {e.code}: {err_body[:300]}") from e
        except Exception as e:
            raise RuntimeError(f"Supabase request failed: {e}") from e

    def put_share(
        self,
        short_id: str,
        ciphertext: str,
        *,
        expires_at: float = 0,
        max_uses: int = 0,
    ) -> Dict[str, Any]:
        """Insert encrypted payload via RPC. Password is NOT stored."""
        ct_len = len(ciphertext or "")
        if ct_len > MAX_CIPHERTEXT_CHARS:
            return {
                "success": False,
                "error": (
                    f"ciphertext too large ({ct_len} chars; max {MAX_CIPHERTEXT_CHARS}). "
                    "Share a site-scoped session (filter domains/storage) or transfer the "
                    ".tokenade file directly — full-profile dumps exceed remote share limits."
                ),
                "short_id": short_id,
                "code": "payload_too_large",
                "ciphertext_chars": ct_len,
                "max_chars": MAX_CIPHERTEXT_CHARS,
            }
        if ct_len < 16:
            return {
                "success": False,
                "error": "invalid ciphertext (too short)",
                "short_id": short_id,
                "code": "invalid_ciphertext",
            }

        exp_iso = None
        if expires_at and expires_at > 0:
            exp_iso = datetime.fromtimestamp(
                expires_at, tz=timezone.utc
            ).isoformat()

        try:
            result = self._rpc(
                "tokenade_put_share",
                {
                    "p_short_id": short_id,
                    "p_ciphertext": ciphertext,
                    "p_expires_at": exp_iso,
                    "p_max_uses": int(max_uses or 0),
                },
            )
        except RuntimeError as e:
            err = str(e)
            code = "remote_error"
            low = err.lower()
            if "too large" in low or "invalid ciphertext" in low:
                code = "payload_too_large"
            elif "timeout" in low or "timed out" in low:
                code = "timeout"
            return {
                "success": False,
                "error": err,
                "short_id": short_id,
                "code": code,
            }

        if isinstance(result, dict) and result.get("success"):
            return {
                "success": True,
                "short_id": short_id,
                "row": result,
                "source": self.config.source,
            }
        return {
            "success": False,
            "error": str(result),
            "short_id": short_id,
        }

    def get_share(self, short_id: str) -> Optional[Dict[str, Any]]:
        """Fetch + consume one use via RPC. Returns row dict or None."""
        result = self._rpc("tokenade_get_share", {"p_short_id": short_id})
        if result is None:
            return None
        if isinstance(result, dict) and result.get("error"):
            # Surface structured errors to caller
            return {
                "error": result["error"],
                "revoked": result["error"] == "revoked",
                "short_id": short_id,
            }
        if isinstance(result, dict) and result.get("ciphertext"):
            return result
        return None

    def peek_share(self, short_id: str) -> Optional[Dict[str, Any]]:
        """Metadata only (no consume)."""
        result = self._rpc("tokenade_peek_share", {"p_short_id": short_id})
        if not result or not isinstance(result, dict):
            return None
        return result

    def increment_uses(self, short_id: str, current_uses: int = 0) -> None:
        """No-op: use count is bumped inside tokenade_get_share."""
        return None

    def revoke(self, short_id: str) -> bool:
        try:
            result = self._rpc("tokenade_revoke_share", {"p_short_id": short_id})
            return bool(isinstance(result, dict) and result.get("success"))
        except Exception as e:
            logger.debug("revoke failed: %s", e)
            return False


def supabase_public_url(short_id: str) -> str:
    """Canonical share reference for receivers (CLI understands this)."""
    return f"tokenade://share/{short_id}"
