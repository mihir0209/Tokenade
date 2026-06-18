"""Session Comparison Tool - Compare two .tokenade session files."""

import json
import logging
from typing import Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DiffResult:
    """Result of comparing two sessions."""
    cookies_only_in_a: List[Dict] = field(default_factory=list)
    cookies_only_in_b: List[Dict] = field(default_factory=list)
    cookies_common: List[Dict] = field(default_factory=list)
    cookies_modified: List[Dict] = field(default_factory=list)
    localStorage_only_in_a: Dict[str, str] = field(default_factory=dict)
    localStorage_only_in_b: Dict[str, str] = field(default_factory=dict)
    localStorage_common: Dict[str, str] = field(default_factory=dict)
    localStorage_modified: Dict[str, Dict] = field(default_factory=dict)
    metadata_diffs: Dict[str, Dict] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.cookies_only_in_a
            or self.cookies_only_in_b
            or self.cookies_modified
            or self.localStorage_only_in_a
            or self.localStorage_only_in_b
            or self.localStorage_modified
            or self.metadata_diffs
        )

    def summary(self) -> str:
        lines = []
        if self.cookies_only_in_a:
            lines.append(f"  Cookies only in A: {len(self.cookies_only_in_a)}")
        if self.cookies_only_in_b:
            lines.append(f"  Cookies only in B: {len(self.cookies_only_in_b)}")
        if self.cookies_modified:
            lines.append(f"  Cookies modified: {len(self.cookies_modified)}")
        if self.localStorage_only_in_a:
            lines.append(f"  localStorage only in A: {len(self.localStorage_only_in_a)} keys")
        if self.localStorage_only_in_b:
            lines.append(f"  localStorage only in B: {len(self.localStorage_only_in_b)} keys")
        if self.localStorage_modified:
            lines.append(f"  localStorage modified: {len(self.localStorage_modified)} keys")
        if self.metadata_diffs:
            lines.append(f"  Metadata differences: {list(self.metadata_diffs.keys())}")
        return "\n".join(lines) if lines else "  Sessions are identical"


class SessionComparator:
    """Compare two .tokenade session files."""

    def load_session(self, path: str) -> Dict:
        """Load a .tokenade file."""
        with open(path, "r") as f:
            return json.load(f)

    def compare(self, session_a: Dict, session_b: Dict) -> DiffResult:
        """Compare two session packages."""
        result = DiffResult()

        # Compare cookies
        cookies_a = {self._cookie_key(c): c for c in session_a.get("cookies", [])}
        cookies_b = {self._cookie_key(c): c for c in session_b.get("cookies", [])}

        keys_a = set(cookies_a.keys())
        keys_b = set(cookies_b.keys())

        for key in keys_a - keys_b:
            result.cookies_only_in_a.append(cookies_a[key])
        for key in keys_b - keys_a:
            result.cookies_only_in_b.append(cookies_b[key])
        for key in keys_a & keys_b:
            ca, cb = cookies_a[key], cookies_b[key]
            if ca.get("value") != cb.get("value"):
                result.cookies_modified.append({"key": key, "a": ca, "b": cb})
            else:
                result.cookies_common.append(ca)

        # Compare localStorage
        ls_a = session_a.get("local_storage") or {}
        ls_b = session_b.get("local_storage") or {}

        keys_ls_a = set(ls_a.keys())
        keys_ls_b = set(ls_b.keys())

        for key in keys_ls_a - keys_ls_b:
            result.localStorage_only_in_a[key] = ls_a[key]
        for key in keys_ls_b - keys_ls_a:
            result.localStorage_only_in_b[key] = ls_b[key]
        for key in keys_ls_a & keys_ls_b:
            if ls_a[key] != ls_b[key]:
                result.localStorage_modified[key] = {"a": ls_a[key], "b": ls_b[key]}
            else:
                result.localStorage_common[key] = ls_a[key]

        # Compare metadata
        for fld in ("site_name", "auth_status", "version", "created_at"):
            va = session_a.get(fld)
            vb = session_b.get(fld)
            if va != vb:
                result.metadata_diffs[fld] = {"a": va, "b": vb}

        # Compare source_device
        da = session_a.get("source_device", {})
        db = session_b.get("source_device", {})
        for key in set(list(da.keys()) + list(db.keys())):
            if da.get(key) != db.get(key):
                result.metadata_diffs[f"source_device.{key}"] = {"a": da.get(key), "b": db.get(key)}

        return result

    def compare_files(self, path_a: str, path_b: str) -> DiffResult:
        """Compare two .tokenade files."""
        session_a = self.load_session(path_a)
        session_b = self.load_session(path_b)
        return self.compare(session_a, session_b)

    def _cookie_key(self, cookie: Dict) -> str:
        """Generate a unique key for a cookie."""
        return f"{cookie.get('domain', '')}|{cookie.get('path', '')}|{cookie.get('name', '')}"
