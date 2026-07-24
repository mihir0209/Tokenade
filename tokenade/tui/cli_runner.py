"""Run tokenade CLI commands from the TUI via subprocess.

KISS: TUI never reimplements CLI logic — it builds argv and runs
`python3 -m tokenade ...` (or sys.executable -m tokenade).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence


LogFn = Callable[[str], None]


@dataclass
class CliResult:
    argv: List[str]
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    pid: int = 0
    log_path: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.error

    @property
    def output(self) -> str:
        parts = [p for p in (self.stdout, self.stderr, self.error) if p]
        return "\n".join(parts).strip()

    @property
    def cmdline(self) -> str:
        return " ".join(shlex.quote(a) for a in self.argv)


def tokenade_argv(*args: str) -> List[str]:
    """Build argv for repo-local / current-interpreter tokenade."""
    return [sys.executable, "-m", "tokenade", *args]


def _bg_log_dir() -> Path:
    d = Path.home() / ".tokenade" / "logs" / "tui-cli"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_tokenade(
    args: Sequence[str],
    *,
    timeout: Optional[float] = None,
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
    background: bool = False,
    on_line: Optional[LogFn] = None,
) -> CliResult:
    """
    Run `python -m tokenade <args>`.

    background=True: keep process alive (launch). Logs go to
    ~/.tokenade/logs/tui-cli/ so failures are visible; we also poll ~2s
    to catch immediate crashes (e.g. cloak CDP fail).
    """
    argv = tokenade_argv(*[str(a) for a in args])
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env.setdefault("PYTHONUNBUFFERED", "1")

    if background:
        log_path = _bg_log_dir() / f"{int(time.time())}_{args[0] if args else 'cmd'}.log"
        try:
            log_f = open(log_path, "w", buffering=1)
            log_f.write(f"$ {' '.join(shlex.quote(a) for a in argv)}\n\n")
            log_f.flush()
            proc = subprocess.Popen(
                argv,
                env=run_env,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            # Detect instant death (cloak CDP, missing browser, etc.)
            time.sleep(2.0)
            code = proc.poll()
            try:
                log_f.flush()
            except Exception:
                pass
            tail = ""
            try:
                tail = Path(log_path).read_text(errors="replace")[-2500:]
            except Exception:
                pass
            if code is not None:
                return CliResult(
                    argv=argv,
                    returncode=code,
                    stdout=tail,
                    error=f"process exited early code={code}",
                    pid=proc.pid or 0,
                    log_path=str(log_path),
                )
            return CliResult(
                argv=argv,
                returncode=0,
                stdout=f"running pid={proc.pid}\nlog={log_path}\n{tail[-800:]}",
                pid=proc.pid or 0,
                log_path=str(log_path),
            )
        except Exception as e:
            return CliResult(argv=argv, returncode=1, error=str(e))

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=run_env,
            cwd=cwd,
        )
        if on_line:
            for line in (completed.stdout or "").splitlines():
                on_line(line)
            for line in (completed.stderr or "").splitlines():
                on_line(line)
        return CliResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"")
        err = (e.stderr or b"")
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        if isinstance(err, bytes):
            err = err.decode(errors="replace")
        return CliResult(
            argv=argv,
            returncode=124,
            stdout=out,
            stderr=err,
            error=f"timed out after {timeout}s",
        )
    except Exception as e:
        return CliResult(argv=argv, returncode=1, error=str(e))


def run_tokenade_async(
    args: Sequence[str],
    *,
    on_done: Callable[[CliResult], None],
    timeout: Optional[float] = None,
    background: bool = False,
) -> threading.Thread:
    """Fire-and-forget worker thread; calls on_done(result) on completion."""

    def _worker():
        result = run_tokenade(args, timeout=timeout, background=background)
        try:
            on_done(result)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True, name="tokenade-cli")
    t.start()
    return t


def cmd_health(session_file: str) -> List[str]:
    return ["health", "-s", session_file]


def cmd_launch(
    session_file: str,
    *,
    browser: str = "cloak",
    url: str = "",
    visible: bool = True,
    proxy: str = "",
    port: int = 0,
    profile: str = "",
) -> List[str]:
    args = ["launch", "-s", session_file, "-b", browser]
    if visible:
        args.append("--visible")
    else:
        args.append("--headless")
    if url:
        args.extend(["-u", url])
    if proxy:
        args.extend(["--proxy", proxy])
    if port:
        args.extend(["-p", str(port)])
    if profile:
        args.extend(["--profile", profile])
    return args


def cmd_load(
    session_file: str,
    *,
    visible: bool = True,
    validate: bool = False,
    stealth_level: str = "maximum",
) -> List[str]:
    args = [
        "load",
        "--file", session_file,
        "--stealth-level", stealth_level,
    ]
    if visible:
        args.append("--visible")
    if validate:
        args.append("--validate")
    return args


def cmd_refresh_browser(
    session_file: str,
    *,
    browser: str = "cloak",
    url: str = "",
    headless: bool = True,
) -> List[str]:
    """Build refresh-browser argv. Defaults headless — always exits after login check."""
    args = ["refresh-browser", "-s", session_file, "-b", browser]
    if headless:
        args.append("--headless")
    if url:
        args.extend(["-u", url])
    return args


def cmd_export(
    *,
    browser_name: str = "",
    profile: str = "",
    domains: str = "",
    output: str = "",
    full: bool = True,
    list_profiles: bool = False,
    list_handlers: bool = False,
    cdp_port: str | int = "",
    encrypt_password: str = "",
    plugin: str = "",
    proxy_plugin: str = "",
    no_plugin: bool = False,
    collect_fingerprint: bool = False,
    browser_path: str = "",
) -> List[str]:
    """Build export argv matching ``tokenade export`` CLI flags."""
    args: List[str] = ["export"]
    if list_profiles:
        args.append("--list-profiles")
        return args
    if list_handlers:
        args.append("--list-handlers")
        return args
    if browser_name:
        args.extend(["--browser-name", browser_name])
    if browser_path:
        args.extend(["--browser-path", browser_path])
    if profile:
        args.extend(["--profile", profile])
    if domains:
        args.extend(["--domains", domains])
    if output:
        args.extend(["--output", output])
    if full:
        args.append("--full")
    if cdp_port not in ("", None, 0, "0"):
        args.extend(["--cdp-port", str(cdp_port)])
    if encrypt_password:
        args.extend(["--encrypt-password", encrypt_password])
    if plugin:
        args.extend(["--plugin", plugin])
    if proxy_plugin:
        args.extend(["--proxy-plugin", proxy_plugin])
    if no_plugin:
        args.append("--no-plugin")
    if collect_fingerprint:
        args.append("--collect-fingerprint")
    return args


def format_receive_help(
    *,
    short_id: str,
    full_url: str,
    short_url: str = "",
    password_hint: str = "YOUR_PASSWORD",
    output: str = "received.tokenade",
    remote: bool = False,
) -> str:
    """Human-readable how-to after creating a share."""
    lines = [
        "How the receiver imports this session:",
        "",
        "  # By short id (works if Supabase remote is configured on both sides):",
        f"  python3 -m tokenade share-url retrieve {short_id} \\",
        f"      --password '{password_hint}' -o {output}",
        "",
        "  # Or paste the full URL (payload embedded — no server needed):",
        f"  python3 -m tokenade share-url retrieve '{_clip(full_url, 80)}' \\",
        f"      --password '{password_hint}' -o {output}",
    ]
    if remote:
        lines += [
            "",
            "  Transport: Supabase (ciphertext only; password never stored).",
            "  Short-id works with public default remote or your private project.",
        ]
    else:
        lines += [
            "",
            "  Transport: embedded full URL only (no remote store).",
            "  Public default remote is on unless disabled (share-url status).",
        ]
    if short_url and short_url != full_url and not short_url.startswith("tokenade://"):
        lines += ["", f"  HTTP short link: {short_url}"]
    lines += [
        "",
        "Then load it:",
        f"  python3 -m tokenade load --file {output} --visible",
        f"  python3 -m tokenade launch -s {output} --visible",
        "",
        "Note: tokenade:// is CLI-only — not a browser protocol.",
    ]
    return "\n".join(lines)


def _clip(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def copy_text(text: str) -> tuple[bool, str]:
    """Best-effort clipboard. Returns (ok, method)."""
    if not text:
        return False, "empty"
    # 1) xclip
    try:
        p = subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode(),
            capture_output=True,
            timeout=2,
        )
        if p.returncode == 0:
            return True, "xclip"
    except Exception:
        pass
    # 2) xsel
    try:
        p = subprocess.run(
            ["xsel", "--clipboard", "--input"],
            input=text.encode(),
            capture_output=True,
            timeout=2,
        )
        if p.returncode == 0:
            return True, "xsel"
    except Exception:
        pass
    # 3) wl-copy (wayland)
    try:
        p = subprocess.run(
            ["wl-copy"],
            input=text.encode(),
            capture_output=True,
            timeout=2,
        )
        if p.returncode == 0:
            return True, "wl-copy"
    except Exception:
        pass
    # 4) OSC 52 (works in many modern terminals / tmux with set-clipboard)
    try:
        import base64
        b64 = base64.b64encode(text.encode()).decode()
        # wrap for tmux if needed
        seq = f"\033]52;c;{b64}\a"
        sys.stdout.write(seq)
        sys.stdout.flush()
        return True, "osc52"
    except Exception:
        pass
    return False, "none"
