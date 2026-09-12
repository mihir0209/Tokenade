"""Sessions browser — compact tiles + CLI action buttons."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from textual.app import ComposeResult
    from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical
    from textual.widgets import Static, Button, Input, Select, Label, RichLog
    from textual.widget import Widget
    _OK = True
except ImportError:
    _OK = False

    class Widget:
        pass

    class ComposeResult:
        pass

    class Grid:
        pass

    class Horizontal:
        pass

    class ScrollableContainer:
        pass

    class Vertical:
        pass

    class Static:
        pass

    class Button:
        pass

    class Input:
        pass

    class Select:
        pass

    class Label:
        pass

    class RichLog:
        pass

    class Rule:
        pass


from tokenade.tui.config import SESSIONS_DIR
from tokenade.tui.ids import safe_id
from tokenade.tui.views.base import BaseView


def launch_browser_options(*, refresh: bool = False) -> List[Tuple[str, str]]:
    """Dynamic browser list from one profile discovery pass (cached)."""
    try:
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

        discovery = BrowserProfileDiscovery()
        if refresh:
            discovery.refresh_cache()
        return discovery.list_launch_browsers(use_cache=True)
    except Exception:
        return [("cloak", "cloak")]


def launch_profile_options(browser: str, *, refresh: bool = False) -> List[Tuple[str, str]]:
    """Profile names for the selected browser (cached discovery)."""
    try:
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

        discovery = BrowserProfileDiscovery()
        if refresh:
            discovery.refresh_cache()
        return discovery.list_profiles_for_browser(browser, use_cache=True)
    except Exception:
        from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery

        return [("clean profile", BrowserProfileDiscovery.CLEAN_PROFILE_VALUE)]


# Short site_name → product URL (when cookies alone are ambiguous)
_SITE_URL_MAP = {
    "spotify": "https://open.spotify.com",
    "google": "https://myaccount.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "amazon": "https://www.amazon.com",
    "facebook": "https://www.facebook.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "youtube": "https://www.youtube.com",
    "discord": "https://discord.com/channels/@me",
    "netflix": "https://www.netflix.com",
    "instagram": "https://www.instagram.com",
    "slack": "https://slack.com",
}


def detect_session_url(data: Dict[str, Any]) -> str:
    """Best-effort redirect URL from a loaded .tokenade dict."""
    if not isinstance(data, dict):
        return ""
    # Explicit fields first
    for key in ("target_url", "url", "dashboard_url", "start_url"):
        val = data.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    for key in ("target_url", "url", "dashboard_url", "refresh_url", "last_url"):
        val = meta.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    # Cookie-domain rules (same spirit as CLI)
    cookies = data.get("cookies") or []
    try:
        from tokenade.cli.handlers.browser_ops import _detect_url_from_cookies
        detected = _detect_url_from_cookies(cookies)
        if detected:
            return detected
    except Exception:
        pass
    site = str(data.get("site_name") or data.get("site") or "").strip()
    if not site or site.lower() in ("unknown", "session-backup", "backup"):
        return ""
    mapped = _SITE_URL_MAP.get(site.lower())
    if mapped:
        return mapped
    if "." in site:
        return f"https://{site.lstrip('.')}"
    return ""


def load_sessions(sessions_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load .tokenade files from sessions_dir (default ~/.tokenade/sessions).

    Includes corrupt/empty files so they remain visible (with health=0) instead
    of silently vanishing from the TUI.
    """
    root = Path(sessions_dir or SESSIONS_DIR)
    out: List[Dict[str, Any]] = []
    if not root.exists():
        return out
    now = time.time()
    for f in sorted(root.glob("*.tokenade")):
        size = 0
        try:
            size = f.stat().st_size
        except OSError:
            continue
        entry: Dict[str, Any] = {
            "name": f.stem,
            "file": str(f),
            "site": "unknown",
            "auth": "unknown",
            "cookies": 0,
            "expired": 0,
            "health": 0.0,
            "url": "",
            "corrupt": False,
            "size": size,
        }
        if size <= 0:
            entry["corrupt"] = True
            entry["auth"] = "empty"
            out.append(entry)
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                raw = fh.read().strip()
            if not raw:
                entry["corrupt"] = True
                entry["auth"] = "empty"
                out.append(entry)
                continue
            data = json.loads(raw)
            if not isinstance(data, dict):
                entry["corrupt"] = True
                entry["auth"] = "invalid"
                out.append(entry)
                continue
            cookies = data.get("cookies") or []
            expired = 0
            for c in cookies:
                if not isinstance(c, dict):
                    continue
                exp = c.get("expires") or c.get("expiry") or 0
                try:
                    exp_i = int(exp)
                except (TypeError, ValueError):
                    continue
                if exp_i <= 0:
                    continue
                if exp_i > 10_000_000_000:
                    exp_i //= 1000
                if exp_i < now:
                    expired += 1
            total = len(cookies)
            health = ((total - expired) / total * 100.0) if total else 0.0
            entry.update({
                "site": data.get("site_name") or data.get("site") or "unknown",
                "auth": data.get("auth_status") or "unknown",
                "cookies": total,
                "expired": expired,
                "health": health,
                "url": detect_session_url(data),
                "corrupt": False,
            })
            try:
                from tokenade.core.artifacts import ProfileArtifactManager
                inspection = ProfileArtifactManager.inspect(data)
                entry["access_mode"] = inspection.access_mode.value
                entry["profile_artifact_count"] = inspection.artifact_count
                entry["access_warnings"] = list(inspection.warnings)
            except Exception:
                entry["access_mode"] = "unknown"
                entry["profile_artifact_count"] = 0
        except Exception:
            entry["corrupt"] = True
            entry["auth"] = "corrupt"
        out.append(entry)
    return out


class SessionTile(Widget if _OK else object):
    """Compact session tile for 3-column grid."""

    DEFAULT_CSS = """
    SessionTile {
        width: 1fr;
        height: 6;
        min-height: 6;
        max-height: 6;
        margin: 0 1 1 0;
        padding: 0 1;
        background: $surface;
        border: tall $primary-background-lighten-2;
        layout: vertical;
    }
    SessionTile:hover {
        background: $surface-lighten-1;
        border: tall $primary;
    }
    SessionTile .st-name {
        text-style: bold;
        color: $primary;
        height: 1;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    SessionTile .st-meta {
        color: $text-muted;
        height: 1;
        overflow: hidden;
    }
    SessionTile .st-actions {
        height: 1;
        dock: bottom;
    }
    SessionTile .st-actions Button {
        margin-right: 1;
        min-width: 7;
    }
    SessionTile.-selected {
        border: tall $success;
        background: $surface-lighten-1;
    }
    SessionTile.-corrupt {
        border: tall $error;
    }
    """

    def __init__(self, session: Dict[str, Any], selected: bool = False, **kwargs):
        if _OK:
            super().__init__(**kwargs)
        self.session = session
        self._selected = selected

    def on_mount(self):
        if not _OK:
            return
        if self._selected:
            self.add_class("-selected")
        if self.session.get("corrupt"):
            self.add_class("-corrupt")

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        s = self.session
        name = s.get("name", "?")
        health = s.get("health", 0)
        if s.get("corrupt"):
            mark = "!"
        else:
            mark = "●" if health >= 80 else ("○" if health >= 50 else "✗")
        yield Static(f"{mark} {name}", classes="st-name")
        if s.get("corrupt"):
            yield Static(
                f"CORRUPT/EMPTY · {s.get('size', 0)} B · re-export needed",
                classes="st-meta",
            )
        else:
            yield Static(
                f"{s.get('site', '?')} · {s.get('cookies', 0)} ck · "
                f"{health:.0f}% · {s.get('auth', '?')} · {s.get('access_mode', 'clone')}",
                classes="st-meta",
            )
        yield Horizontal(
            Button("Sel", variant="default", compact=True, id=safe_id("select-", name)),
            Button("Health", variant="primary", compact=True, id=safe_id("health-", name)),
            Button("Del", variant="error", compact=True, id=safe_id("delete-", name)),
            classes="st-actions",
        )


class SessionGrid(Grid if _OK else object):
    DEFAULT_CSS = """
    SessionGrid {
        grid-size: 3;
        grid-gutter: 0 1;
        grid-rows: auto;
        height: auto;
        padding: 0 1;
        align: left top;
    }
    """

    def __init__(self, **kwargs):
        if _OK:
            super().__init__(**kwargs)


class SessionsView(BaseView):
    DEFAULT_CSS = """
    SessionsView {
        height: 1fr;
        layout: vertical;
        align: left top;
    }
    SessionsView #sessions-list {
        height: 1fr;
        overflow-y: auto;
        padding: 0;
        align: left top;
    }
    SessionsView .action-bar {
        height: auto;
        max-height: 18;
        padding: 0 1 1 1;
        border-top: solid $primary-background-lighten-2;
    }
    SessionsView .action-bar .field-label {
        color: $text-muted;
        height: 1;
        margin-top: 0;
    }
    SessionsView .action-row {
        height: 3;
        align: left middle;
    }
    SessionsView .action-row Button, SessionsView .action-row Select, SessionsView .action-row Input {
        margin-right: 1;
    }
    SessionsView .action-row #session-browser-select { width: 28; min-width: 22; }
    SessionsView .action-row #session-profile-select { width: 42; min-width: 32; }
    SessionsView .action-row #session-url-input { width: 44; max-width: 56; }
    SessionsView #session-cli-log {
        height: 10;
        max-height: 12;
        min-height: 6;
        background: $surface;
        border: tall $primary-background-lighten-2;
        scrollbar-size: 1 1;
    }
    SessionsView #session-selected-label {
        text-style: bold;
        color: $success;
        height: 1;
    }
    """

    def compose(self) -> "ComposeResult":
        if not _OK:
            return
        yield from self.compose_title("📁 Sessions", f"{SESSIONS_DIR}")
        yield ScrollableContainer(SessionGrid(id="session-grid"), id="sessions-list")
        with Vertical(classes="action-bar"):
            yield Static("No session selected — click Sel on a tile", id="session-selected-label")
            yield Label(
                "Launch = inject+navigate (stays open) · Load = Playwright inject (stays open) · "
                "Refresh = inject→check login→save→close",
                classes="field-label",
            )
            opts = launch_browser_options()
            default_browser = next(
                (v for _, v in opts if v == "cloak"),
                opts[0][1] if opts else "cloak",
            )
            prof_opts = launch_profile_options(default_browser)
            default_prof = prof_opts[0][1] if prof_opts else "__clean__"
            for label, val in prof_opts:
                if "· default" in label or label.endswith(" default"):
                    default_prof = val
                    break
            yield Horizontal(
                Select(
                    opts,
                    id="session-browser-select",
                    value=default_browser,
                    allow_blank=False,
                ),
                Select(
                    prof_opts,
                    id="session-profile-select",
                    value=default_prof,
                    allow_blank=False,
                ),
                Input(placeholder="URL", id="session-url-input"),
                classes="action-row",
            )
            yield Horizontal(
                Button("Launch", variant="success", compact=True, id="session-launch"),
                Button("Load", variant="primary", compact=True, id="session-load"),
                Button("Refresh", variant="warning", compact=True, id="session-refresh"),
                Button("Health CLI", variant="default", compact=True, id="session-health-cli"),
                Button("Share…", variant="default", compact=True, id="session-share"),
                Button("Copy path", variant="default", compact=True, id="session-copy-path"),
                classes="action-row",
            )
            yield RichLog(
                id="session-cli-log",
                highlight=True,
                markup=True,
                max_lines=200,
                wrap=True,
                auto_scroll=True,
            )
