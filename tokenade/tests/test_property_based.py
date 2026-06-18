"""
Property-based tests using Hypothesis.

Tests invariants that must hold for all possible inputs.
"""
import pytest
from hypothesis import given, strategies as st, assume, settings, HealthCheck
import json

# Only run if hypothesis is available
hypothesis = pytest.importorskip("hypothesis")


# Strategies for cookie data
cookie_strategy = st.fixed_dictionaries({
    "name": st.text(min_size=1, max_size=50).filter(lambda x: x.isidentifier() or x.replace("_", "").replace("-", "").isalnum()),
    "value": st.text(min_size=0, max_size=200),
    "domain": st.sampled_from([".example.com", ".google.com", ".github.com", ".test.org"]),
    "path": st.sampled_from(["/", "/api", "/auth", "/settings"]),
    "secure": st.booleans(),
    "httpOnly": st.booleans(),
    "sameSite": st.sampled_from(["Strict", "Lax", "None", ""]),
    "expires": st.one_of(
        st.integers(min_value=0, max_value=4000000000),
        st.just(0),
        st.just(-1),
    ),
})

session_strategy = st.fixed_dictionaries({
    "version": st.just("2.0"),
    "created_at": st.sampled_from(["2026-01-01T00:00:00Z", "2025-06-15T12:30:00Z", "2099-12-31T23:59:59Z"]),
    "site_name": st.sampled_from(["google", "github", "twitter", "test", "example"]),
    "auth_status": st.sampled_from(["logged_in", "logged_out", "unknown"]),
    "cookies": st.lists(cookie_strategy, min_size=0, max_size=50),
})


class TestFormatExporterProperties:
    """Property-based tests for FormatExporter."""

    @given(session_strategy)
    @settings(max_examples=50)
    def test_playwright_storagestate_is_valid_json(self, session):
        """Playwright storageState output must always be valid JSON."""
        from tokenade.core.importer.format_exporter import FormatExporter
        exporter = FormatExporter(session)
        result = exporter.to_playwright_storagestate()
        parsed = json.loads(result)
        assert "cookies" in parsed
        assert isinstance(parsed["cookies"], list)

    @given(session_strategy)
    @settings(max_examples=50)
    def test_puppeteer_cookies_is_valid_json(self, session):
        """Puppeteer cookie output must always be valid JSON list."""
        from tokenade.core.importer.format_exporter import FormatExporter
        exporter = FormatExporter(session)
        result = exporter.to_puppeteer_cookies()
        assert isinstance(result, list)
        for cookie in result:
            assert "name" in cookie
            assert "value" in cookie
            assert "domain" in cookie

    @given(session_strategy)
    @settings(max_examples=50)
    def test_netscape_format_starts_with_header(self, session):
        """Netscape format must start with comment header."""
        from tokenade.core.importer.format_exporter import FormatExporter
        exporter = FormatExporter(session)
        result = exporter.to_netscape()
        assert result.startswith("# Netscape HTTP Cookie File") or result == ""

    @given(session_strategy)
    @settings(max_examples=50)
    def test_cookie_header_format(self, session):
        """Cookie header must be name=value pairs separated by semicolons."""
        from tokenade.core.importer.format_exporter import FormatExporter
        exporter = FormatExporter(session)
        result = exporter.to_cookie_header()
        if session.get("cookies"):
            assert "=" in result or result == ""
            # Each pair should have =
            for pair in result.split("; "):
                if pair:
                    assert "=" in pair
        else:
            assert result == ""

    @given(session_strategy)
    @settings(max_examples=50)
    def test_json_roundtrip_preserves_data(self, session):
        """JSON export should preserve session data."""
        from tokenade.core.importer.format_exporter import FormatExporter
        exporter = FormatExporter(session)
        result = exporter.to_json()
        parsed = json.loads(result)
        assert parsed["version"] == session["version"]
        assert len(parsed["cookies"]) == len(session["cookies"])


class TestSessionPackagerProperties:
    """Property-based tests for SessionPackager."""

    @given(st.lists(cookie_strategy, min_size=1, max_size=30))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.filter_too_much])
    def test_package_preserves_cookie_count(self, cookies):
        """Package should preserve all cookies."""
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        result = packager.package(cookies=cookies, browser="chrome", profile="default")
        assert len(result["cookies"]) == len(cookies)

    @given(st.lists(cookie_strategy, min_size=1, max_size=30))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.filter_too_much])
    def test_package_has_required_fields(self, cookies):
        """Package must have all required fields."""
        from tokenade.core.importer.session_packager import SessionPackager
        packager = SessionPackager()
        result = packager.package(cookies=cookies)
        assert "version" in result
        assert "created_at" in result
        assert "cookies" in result
        assert "metadata" in result
        assert "cookie_count" in result["metadata"]


class TestLRUCacheProperties:
    """Property-based tests for LRU cache."""

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=20)
    def test_cache_never_exceeds_max_size(self, max_size):
        """Cache should never have more items than max_size."""
        from tokenade.core.utils.performance import LRUCache
        cache = LRUCache(max_size=max_size, default_ttl=300)
        for i in range(max_size + 10):
            cache.set(f"key_{i}", f"value_{i}")
        assert len(cache) <= max_size

    @given(st.text(min_size=1, max_size=50), st.text(min_size=0, max_size=200))
    @settings(max_examples=50)
    def test_cache_set_get_roundtrip(self, key, value):
        """Setting and getting a key should return the same value."""
        from tokenade.core.utils.performance import LRUCache
        assume("\x00" not in key)  # Skip null bytes
        cache = LRUCache(max_size=100, default_ttl=300)
        cache.set(key, value)
        result = cache.get(key)
        assert result == value


class TestHealthScorerProperties:
    """Property-based tests for health scorer."""

    @given(session_strategy)
    @settings(max_examples=50)
    def test_score_always_between_0_and_100(self, session):
        """Health score must always be 0-100."""
        from tokenade.core.refresh.health_scorer import SessionHealthScorer
        scorer = SessionHealthScorer()
        result = scorer.score(session)
        assert 0 <= result.total_score <= 100

    @given(st.just({"cookies": [], "auth_status": "logged_out", "site_name": "test"}))
    def test_empty_session_scores_zero(self, session):
        """Empty session should score 0."""
        from tokenade.core.refresh.health_scorer import SessionHealthScorer
        scorer = SessionHealthScorer()
        result = scorer.score(session)
        assert result.total_score == 0.0


class TestVaultProperties:
    """Property-based tests for session vault."""

    @given(
        session_id=st.text(min_size=1, max_size=50).filter(lambda x: "\x00" not in x and x.isalnum() and x != "test"),
        max_versions=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20)
    def test_vault_max_versions_respected(self, session_id, max_versions):
        """Vault should never keep more versions than max_versions."""
        from tokenade.core.importer.session_vault import SessionVault
        import tempfile
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            vault = SessionVault(tmpdir, max_versions=max_versions)

            # Create a dummy session file in a separate directory
            source_dir = Path(tmpdir) / "source"
            source_dir.mkdir()
            session_file = source_dir / "test.tokenade"
            session_data = {
                "version": "2.0",
                "site_name": "test",
                "cookies": [{"name": "c", "value": "v", "domain": ".test.com", "path": "/"}],
            }
            session_file.write_text(json.dumps(session_data))

            # Add initial
            sid = vault.add(str(session_file), session_id=session_id)

            # Update multiple times
            for i in range(max_versions + 5):
                session_data["cookies"][0]["value"] = f"v{i}"
                session_file.write_text(json.dumps(session_data))
                vault.update(sid, str(session_file))

            entry = vault._index.get(sid)
            assert len(entry.versions) <= max_versions
