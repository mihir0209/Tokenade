"""Local share-store compaction and oversized embed pruning."""

import json
import time
from pathlib import Path

from tokenade.core.sharing.url_shortener import SessionURLShortener, URLShortenerConfig


def _shortener(tmp_path: Path) -> SessionURLShortener:
    s = SessionURLShortener(URLShortenerConfig())
    s._url_store = tmp_path / "shortened_urls.json"
    s._urls = {}
    return s


def test_strip_embedded_data():
    base = "tokenade://share/abc123"
    huge = base + "?data=" + ("x" * 100_000)
    assert SessionURLShortener._strip_embedded_data(huge) == base
    assert SessionURLShortener._strip_embedded_data(base) == base
    assert SessionURLShortener._strip_embedded_data("") == ""


def test_prune_oversized_embeds(tmp_path):
    s = _shortener(tmp_path)
    now = time.time()
    from tokenade.core.sharing.url_shortener import ShortenedURL

    s._urls["keep"] = ShortenedURL(
        short_id="keep",
        original_url="tokenade://share/keep",
        short_url="tokenade://share/keep",
        created_at=now,
        expires_at=now + 3600,
    )
    big = "tokenade://share/big?data=" + ("Z" * 80_000)
    s._urls["big"] = ShortenedURL(
        short_id="big",
        original_url=big,
        short_url=big,
        created_at=now,
        expires_at=now + 3600,
    )
    s._save_urls()
    stats = s.prune_oversized_embeds()
    assert stats["stripped"] == 1
    assert stats["removed"] == 0
    assert s._urls["big"].original_url == "tokenade://share/big"
    assert "?data=" not in (s._urls["big"].short_url or "")
    assert s._urls["keep"].original_url == "tokenade://share/keep"
    # File on disk is compact
    raw = s._url_store.read_text()
    assert len(raw) < 5_000
    assert "?data=" not in raw


def test_load_compacts_oversized_store(tmp_path):
    store = tmp_path / "shortened_urls.json"
    now = time.time()
    payload = [
        {
            "short_id": "fat",
            "original_url": "tokenade://share/fat?data=" + ("Y" * 100_000),
            "short_url": "tokenade://share/fat?data=" + ("Y" * 100_000),
            "created_at": now,
            "expires_at": now + 9999,
            "password_hash": None,
            "max_uses": 0,
            "current_uses": 0,
            "revoked": False,
        }
    ]
    store.write_text(json.dumps(payload))
    # Force size > 1MB so load rewrites (pad file after JSON is awkward; call prune path)
    s = SessionURLShortener(URLShortenerConfig())
    s._url_store = store
    s._urls = {}
    s._load_urls()
    assert "fat" in s._urls
    assert "?data=" not in s._urls["fat"].original_url
    assert s._urls["fat"].original_url == "tokenade://share/fat"


def test_cleanup_local_store_removes_expired(tmp_path):
    s = _shortener(tmp_path)
    now = time.time()
    from tokenade.core.sharing.url_shortener import ShortenedURL

    s._urls["old"] = ShortenedURL(
        short_id="old",
        original_url="tokenade://share/old?data=" + ("Q" * 60_000),
        short_url="tokenade://share/old",
        created_at=now - 10_000,
        expires_at=now - 1,
    )
    s._urls["ok"] = ShortenedURL(
        short_id="ok",
        original_url="tokenade://share/ok",
        short_url="tokenade://share/ok",
        created_at=now,
        expires_at=now + 9999,
    )
    stats = s.cleanup_local_store()
    assert stats["expired"] == 1
    assert "old" not in s._urls
    assert "ok" in s._urls
    assert stats["remaining"] == 1
