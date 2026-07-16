#!/usr/bin/env python3
"""Fail if build artifacts include non-runtime test packages."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from zipfile import ZipFile


def main() -> int:
    with Path("pyproject.toml").open("rb") as f:
        version = tomllib.load(f)["project"]["version"]

    wheels = sorted(Path("dist").glob(f"tokenade-{version}-*.whl"))
    if not wheels:
        print(f"No tokenade {version} wheels found in dist/", file=sys.stderr)
        return 1

    failed = False
    for wheel in wheels:
        with ZipFile(wheel) as archive:
            test_members = [
                name for name in archive.namelist()
                if name.startswith("tokenade/tests/")
            ]

        if test_members:
            failed = True
            print(f"{wheel}: contains tokenade/tests files", file=sys.stderr)
            for name in test_members[:20]:
                print(f"  - {name}", file=sys.stderr)
            if len(test_members) > 20:
                print(f"  ... {len(test_members) - 20} more", file=sys.stderr)
        else:
            print(f"{wheel}: OK")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
