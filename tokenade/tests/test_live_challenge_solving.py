"""
Live challenge SOLVING E2E — runs the CloakBrowser witness in pytest.

Executes scripts/witness_challenge_solvers.py (CloakBrowser stealth Chromium
against real Cloudflare Managed Challenge and Turnstile sites) and asserts all
required checks pass. Skips where Playwright, CloakBrowser, or the witness
script are unavailable.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Real network + browser E2E — slow; deselect with -m "not slow"
pytestmark = [pytest.mark.slow]

pytest.importorskip("playwright")
pytest.importorskip("cloakbrowser")

REPO_ROOT = Path(__file__).resolve().parents[2]
WITNESS = REPO_ROOT / "scripts" / "witness_challenge_solvers.py"


@pytest.mark.skipif(
    not WITNESS.is_file(),
    reason="scripts/witness_challenge_solvers.py not present",
)
@pytest.mark.skipif(
    os.environ.get("CI") and not os.environ.get("TOKENADE_LIVE_NETWORK"),
    reason="live network witness requires TOKENADE_LIVE_NETWORK=1 in CI",
)
class TestLiveChallengeSolving:
    """Live challenge solving against real Cloudflare protections."""

    def test_live_challenge_solving_witness_passes(self):
        result = subprocess.run(
            [sys.executable, str(WITNESS), "--no-screenshots"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"challenge solving witness failed (rc={result.returncode})\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
        assert "RESULT: SUCCESS" in result.stdout
