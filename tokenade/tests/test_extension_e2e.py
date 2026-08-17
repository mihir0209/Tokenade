"""
Browser Extension E2E — runs the live-Chromium witness in pytest.

Executes scripts/witness_extension_e2e.py (headed Chromium with the unpacked
extension loaded) and asserts all checks pass. Skips cleanly where Playwright,
a display, or the witness script is unavailable.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Real browser E2E — slow; deselect with -m "not slow"
pytestmark = [pytest.mark.slow]

pytest.importorskip("playwright")

REPO_ROOT = Path(__file__).resolve().parents[2]
WITNESS = REPO_ROOT / "scripts" / "witness_extension_e2e.py"

_no_display = os.environ.get("DISPLAY", "") == "" and os.environ.get("WAYLAND_DISPLAY", "") == ""
_runs_headless_ci = _no_display and os.environ.get("CI")


@pytest.mark.skipif(
    not WITNESS.is_file(),
    reason="scripts/witness_extension_e2e.py not present",
)
@pytest.mark.skipif(
    _runs_headless_ci,
    reason="headed Chromium (extension load) requires a display",
)
class TestExtensionE2E:
    """Live extension witness in real headed Chromium."""

    def test_extension_witness_passes(self):
        result = subprocess.run(
            [sys.executable, str(WITNESS)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, (
            f"extension witness failed (rc={result.returncode})\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
        assert "RESULT: SUCCESS" in result.stdout
