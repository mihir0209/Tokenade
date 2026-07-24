#!/usr/bin/env python3
"""Apply Tokenade share-store SQL to a private Supabase/Postgres project.

Reads the database URI from the environment only (never hardcode secrets):

  DATABASE_URL=postgresql://postgres....@db.<ref>.supabase.co:5432/postgres
  # or
  SUPABASE_DB_URL=...

Optional: load a local ``.env`` in the repo root or cwd (gitignored).

Usage:
  python3 scripts/apply_supabase_schema.py
  python3 scripts/apply_supabase_schema.py --dry-run
  python3 scripts/apply_supabase_schema.py --verify \\
      --url https://xxxx.supabase.co --anon-key sb_publishable_...

Requires one of: psycopg[binary] / psycopg2 / ``psql`` on PATH.

How public-project restrictions were verified (manual checklist):
  1. RPC put/get/peek/revoke with anon key -> 200 + JSON
  2. Direct REST GET /rest/v1/tokenade_shares -> 401/403 (table revoked from anon)
  3. put with max_uses=0 -> stored as 10; expiry >7d clamped; >30 creates/IP/hour -> error
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def _database_url() -> str:
    for name in ("DATABASE_URL", "SUPABASE_DB_URL", "TOKENADE_DATABASE_URL"):
        v = (os.environ.get(name) or "").strip()
        if v:
            return v
    return ""


def _schema_sql() -> str:
    # Prefer installed/package path so OSS users can run after pip install -e .
    try:
        from tokenade.core.sharing.supabase_store import tokenade_schema_sql

        return tokenade_schema_sql()
    except ImportError:
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        from tokenade.core.sharing.supabase_store import tokenade_schema_sql

        return tokenade_schema_sql()


def _apply_psycopg(dsn: str, sql: str) -> None:
    try:
        import psycopg

        with psycopg.connect(dsn) as conn:
            conn.execute(sql)
            conn.commit()
        return
    except ImportError:
        pass
    try:
        import psycopg2

        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        finally:
            conn.close()
        return
    except ImportError:
        pass
    raise RuntimeError(
        "Need psycopg, psycopg2, or psql. Try: pip install 'psycopg[binary]'"
    )


def _apply_psql(dsn: str, sql: str) -> None:
    psql = shutil.which("psql")
    if not psql:
        raise RuntimeError("psql not found on PATH")
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as fh:
        fh.write(sql)
        path = fh.name
    try:
        subprocess.run(
            [psql, dsn, "-v", "ON_ERROR_STOP=1", "-f", path],
            check=True,
        )
    finally:
        os.unlink(path)


def _verify_rpc(url: str, anon_key: str) -> int:
    """Smoke-check: table denied, RPC callable (peek missing id -> null/empty)."""
    import json
    import urllib.error
    import urllib.request

    base = url.rstrip("/")
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
    }
    rc = 0

    # Direct table must not be open
    req = urllib.request.Request(
        f"{base}/rest/v1/tokenade_shares?select=short_id&limit=1",
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()[:200]
            print(f"[FAIL] direct table GET returned {resp.status}: {body!r}")
            print("       expected 401/403 after revoke all on table from anon")
            rc = 1
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            print(f"[OK]   direct table GET blocked ({e.code})")
        else:
            print(f"[FAIL] direct table GET unexpected HTTP {e.code}")
            rc = 1
    except Exception as e:
        print(f"[FAIL] direct table GET error: {e}")
        rc = 1

    # RPC peek should be executable (null / empty for missing id)
    payload = json.dumps({"p_short_id": "__tokenade_verify_missing__"}).encode()
    req = urllib.request.Request(
        f"{base}/rest/v1/rpc/tokenade_peek_share",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"[OK]   RPC tokenade_peek_share callable ({resp.status}): {body[:80]}")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:200]
        print(f"[FAIL] RPC peek HTTP {e.code}: {err}")
        rc = 1
    except Exception as e:
        print(f"[FAIL] RPC peek error: {e}")
        rc = 1

    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--env-file",
        default="",
        help="Path to .env (default: ./.env then repo-root/.env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL only; do not connect",
    )
    parser.add_argument(
        "--psql",
        action="store_true",
        help="Force apply via psql CLI",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After apply (or alone): check table locked + RPC works",
    )
    parser.add_argument("--url", default="", help="Supabase API URL for --verify")
    parser.add_argument("--anon-key", default="", help="Anon/publishable key for --verify")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    if args.env_file:
        _load_dotenv(Path(args.env_file))
    else:
        _load_dotenv(Path.cwd() / ".env")
        _load_dotenv(repo_root / ".env")

    sql = _schema_sql()
    if args.dry_run:
        print(sql)
        return 0

    dsn = _database_url()
    applied = False
    if dsn:
        print("Applying tokenade_schema_sql() via database URL from env...")
        try:
            if args.psql:
                _apply_psql(dsn, sql)
            else:
                try:
                    _apply_psycopg(dsn, sql)
                except RuntimeError:
                    _apply_psql(dsn, sql)
            print("[OK] schema applied")
            applied = True
        except Exception as e:
            print(f"[ERROR] apply failed: {e}", file=sys.stderr)
            return 1
    elif not args.verify:
        print(
            "[ERROR] No DATABASE_URL / SUPABASE_DB_URL in env or .env\n"
            "  Copy .env.example -> .env and set the Postgres URI from\n"
            "  Supabase Dashboard -> Project Settings -> Database.",
            file=sys.stderr,
        )
        return 1
    else:
        print("[TIP] No DATABASE_URL; skipping apply, verify only")

    if args.verify:
        url = (args.url or os.environ.get("TOKENADE_SUPABASE_URL")
               or os.environ.get("SUPABASE_URL") or "").strip()
        key = (args.anon_key or os.environ.get("TOKENADE_SUPABASE_ANON_KEY")
               or os.environ.get("SUPABASE_ANON_KEY") or "").strip()
        if not url or not key:
            print(
                "[ERROR] --verify needs --url/--anon-key or SUPABASE_URL + SUPABASE_ANON_KEY",
                file=sys.stderr,
            )
            return 1
        print(f"Verifying RPC-only access on {url} ...")
        return _verify_rpc(url, key)

    return 0 if applied else 1


if __name__ == "__main__":
    raise SystemExit(main())
