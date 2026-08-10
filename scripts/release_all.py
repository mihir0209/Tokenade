#!/usr/bin/env python3
"""Fail-closed Tokenade + marketplace release orchestrator."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path


CORE = Path(__file__).resolve().parents[1]
PLUGINS = CORE.parent / "tokenade-plugins"
PAGES_URL = "https://tokenade-plugins.pages.dev"
PAGES_PROJECT = "tokenade-plugins"


def run(*command: str, cwd: Path = CORE, env: dict | None = None) -> None:
    print("==>", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def output(*command: str, cwd: Path = CORE) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def require_clean_pushed(repo: Path) -> str:
    if output("git", "branch", "--show-current", cwd=repo) != "main":
        raise SystemExit(f"{repo}: release requires main branch")
    if output("git", "status", "--porcelain=v1", "--untracked-files=all", cwd=repo):
        raise SystemExit(f"{repo}: worktree is not clean")
    upstream = output("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", cwd=repo)
    remote_name = upstream.split("/", 1)[0]
    run("git", "fetch", "--prune", remote_name, cwd=repo)
    head = output("git", "rev-parse", "HEAD", cwd=repo)
    remote = output("git", "rev-parse", upstream, cwd=repo)
    if head != remote:
        raise SystemExit(f"{repo}: HEAD must equal {upstream}")
    return head


def version() -> str:
    with (CORE / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    import tokenade
    if tokenade.__version__ != project_version:
        raise SystemExit("pyproject and tokenade.__version__ differ")
    return project_version


def ensure_unpublished(release_version: str) -> None:
    try:
        urllib.request.urlopen(
            f"https://pypi.org/pypi/tokenade/{release_version}/json", timeout=30
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return
        raise
    raise SystemExit(f"tokenade=={release_version} already exists on PyPI")


def verify_pages(expected: bytes, cache_key: str, base_url: str = PAGES_URL) -> None:
    deadline = time.monotonic() + 600
    url = f"{base_url.rstrip('/')}/plugins.json?release={cache_key}"
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                if body == expected:
                    if response.headers.get("Access-Control-Allow-Origin") != "*":
                        raise RuntimeError("Pages registry lacks CORS header")
                    return
        except Exception:
            pass
        time.sleep(10)
    raise SystemExit("Cloudflare Pages production registry did not converge")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true", help="Deploy Pages and upload PyPI")
    args = parser.parse_args()
    if not PLUGINS.is_dir():
        raise SystemExit(f"Missing marketplace checkout: {PLUGINS}")

    core_sha = require_clean_pushed(CORE)
    plugins_sha = require_clean_pushed(PLUGINS)
    release_version = version()
    ensure_unpublished(release_version)

    env = dict(os.environ)
    env["TOKENADE_PLUGINS_DIR"] = str(PLUGINS / "plugins")
    run(sys.executable, "-m", "pytest", "tokenade/tests", "tests", "-q", cwd=CORE, env=env)
    run(sys.executable, "-m", "pytest", "tests", "-q", cwd=PLUGINS, env=env)
    run(sys.executable, "scripts/run_contracts.py", cwd=PLUGINS, env=env)
    run(sys.executable, "tools/registry.py", "--check", cwd=PLUGINS)
    run(sys.executable, "scripts/build_pages.py", cwd=PLUGINS)
    run("rm", "-rf", "dist", "build", cwd=CORE)
    run(sys.executable, "-m", "build", cwd=CORE)
    run(sys.executable, "-m", "twine", "check", "--strict", *map(str, sorted((CORE / "dist").iterdir())), cwd=CORE)
    run(sys.executable, "scripts/check_wheel_contents.py", cwd=CORE)
    run(sys.executable, "scripts/smoke_installed_wheel.py", cwd=CORE)

    if not args.publish:
        print("Release validation passed; rerun with --publish to deploy and upload.")
        return 0
    for variable in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "TWINE_USERNAME", "TWINE_PASSWORD"):
        if not os.environ.get(variable):
            raise SystemExit(f"Missing required environment variable: {variable}")

    preview_branch = f"release-{release_version.replace('.', '-')}"
    run(
        "npx", "--yes", "wrangler@4.120.0", "pages", "deploy", "dist-pages",
        "--project-name", PAGES_PROJECT, "--branch", preview_branch,
        "--commit-hash", plugins_sha, "--commit-message", f"Registry for {release_version}",
        "--commit-dirty=false", cwd=PLUGINS,
    )
    expected = (PLUGINS / "plugins.json").read_bytes()
    preview_url = f"https://{preview_branch}.{PAGES_PROJECT}.pages.dev"
    verify_pages(expected, plugins_sha, preview_url)

    with tempfile.TemporaryDirectory(prefix="tokenade-release-") as temporary:
        venv = Path(temporary) / "venv"
        run(sys.executable, "-m", "venv", str(venv))
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        wheel = next((CORE / "dist").glob(f"tokenade-{release_version}-*.whl"))
        run(str(python), "-m", "pip", "install", "--quiet", str(wheel))
        script = (
            "from pathlib import Path; from tokenade.core.integration.plugin_registry import PluginRegistry; "
            f"r=PluginRegistry(plugins_dir=Path(r'{temporary}')/'plugins', registry_url='{preview_url}'); "
            "ps=r._fetch_registry(); assert ps; "
            "assert all(r.install(p['name']) for p in ps); print(len(ps))"
        )
        run(str(python), "-c", script)

    if require_clean_pushed(CORE) != core_sha or require_clean_pushed(PLUGINS) != plugins_sha:
        raise SystemExit("source repositories changed during release validation")

    run(
        sys.executable, "-m", "twine", "upload", "--non-interactive",
        "--disable-progress-bar", *map(str, sorted((CORE / "dist").iterdir())), cwd=CORE,
    )
    run(
        "npx", "--yes", "wrangler@4.120.0", "pages", "deploy", "dist-pages",
        "--project-name", PAGES_PROJECT, "--branch", "main",
        "--commit-hash", plugins_sha, "--commit-message", f"Registry for {release_version}",
        "--commit-dirty=false", cwd=PLUGINS,
    )
    verify_pages(expected, plugins_sha)
    print(f"Released tokenade {release_version}: core={core_sha} plugins={plugins_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
