#!/usr/bin/env python3
"""Smoke-test the built wheel from a clean virtual environment."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"==> {' '.join(command)}")
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.stdout:
        print(result.stdout)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def main() -> int:
    with Path("pyproject.toml").open("rb") as f:
        version = tomllib.load(f)["project"]["version"]

    wheels = sorted(Path("dist").glob(f"tokenade-{version}-*.whl"))
    if not wheels:
        print(f"No tokenade {version} wheels found in dist/", file=sys.stderr)
        return 1

    wheel = wheels[-1].resolve()

    with tempfile.TemporaryDirectory(prefix="tokenade-wheel-smoke.") as tmp:
        tmp_path = Path(tmp)
        venv = tmp_path / "venv"
        run([sys.executable, "-m", "venv", str(venv)])

        bin_dir = "Scripts" if sys.platform == "win32" else "bin"
        python = venv / bin_dir / ("python.exe" if sys.platform == "win32" else "python")
        tokenade = venv / bin_dir / ("tokenade.exe" if sys.platform == "win32" else "tokenade")

        run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
        run([str(python), "-m", "pip", "install", "--no-cache-dir", str(wheel)])
        run([str(tokenade), "--version"])
        run([str(python), "-c", "import tokenade.core.portability"])

        session_file = tmp_path / "minimal.tokenade"
        session_file.write_text(
            json.dumps(
                {
                    "site_name": "wheel-smoke-unknown",
                    "auth_status": "unknown",
                    "cookies": [],
                    "tokens": [],
                }
            ),
            encoding="utf-8",
        )

        result = run([str(tokenade), "test", "-s", str(session_file)], check=False)
        output = result.stdout or ""
        if "No module named" in output or "ModuleNotFoundError" in output:
            print("Installed wheel has a runtime import error", file=sys.stderr)
            return 1
        if "No handler found" not in output:
            print("tokenade test did not reach expected handler-resolution path", file=sys.stderr)
            return 1

    print(f"Installed wheel smoke passed for tokenade=={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
