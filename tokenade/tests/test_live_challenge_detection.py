"""
Live anti-bot Challenge Detection E2E — runs the network witness in pytest.

Executes scripts/witness_challenge_detectors.py (headless Chromium against
real Cloudflare / Akamai / DataDome protected sites) and asserts all required
checks pass. Skips cleanly where Playwright or the witness script is
unavailable.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Real network + browser E2E — slow; deselect with -m "not slow"
pytestmark = [pytest.mark.slow]

pytest.importorskip("playwright")

REPO_ROOT = Path(__file__).resolve().parents[2]
WITNESS = REPO_ROOT / "scripts" / "witness_challenge_detectors.py"


@pytest.mark.skipif(
    not WITNESS.is_file(),
    reason="scripts/witness_challenge_detectors.py not present",
)
@pytest.mark.skipif(
    os.environ.get("CI") and not os.environ.get("TOKENADE_LIVE_NETWORK"),
    reason="live network witness requires TOKENADE_LIVE_NETWORK=1 in CI",
)
class TestLiveChallengeDetection:
    """Live anti-bot challenge detection against real protected sites."""

    def test_live_challenge_detection_witness_passes(self):
        result = subprocess.run(
            [sys.executable, str(WITNESS)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"challenge detection witness failed (rc={result.returncode})\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
        assert "RESULT: SUCCESS" in result.stdout
