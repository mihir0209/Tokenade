"""Read-only checks for plugin runtime and Session requirements."""

from __future__ import annotations

import importlib.metadata
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List

from packaging.requirements import Requirement
from packaging.version import InvalidVersion, Version


@dataclass
class DependencyIssue:
    kind: str
    requirement: str
    reason: str


@dataclass
class DependencyReport:
    issues: List[DependencyIssue] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.issues


def check_runtime_dependencies(manifest: Dict[str, Any]) -> DependencyReport:
    """Check declared Python distributions and system executables."""
    report = DependencyReport()
    runtime = manifest.get("runtime_dependencies") or {}

    for raw in runtime.get("python", []) if isinstance(runtime, dict) else []:
        try:
            requirement = Requirement(str(raw))
        except Exception as exc:
            report.issues.append(DependencyIssue("python", str(raw), f"invalid requirement: {exc}"))
            continue
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            report.issues.append(DependencyIssue("python", str(raw), "not installed"))
            continue
        if requirement.specifier and not requirement.specifier.contains(installed, prereleases=True):
            report.issues.append(
                DependencyIssue("python", str(raw), f"installed version is {installed}")
            )

    for command in runtime.get("system", []) if isinstance(runtime, dict) else []:
        if not shutil.which(str(command)):
            report.issues.append(DependencyIssue("system", str(command), "executable not found"))

    return report


def check_tokenade_compatibility(manifest: Dict[str, Any], current_version: str) -> DependencyReport:
    """Check a plugin manifest against the running Tokenade version."""
    report = DependencyReport()
    try:
        current = Version(current_version)
        minimum = manifest.get("min_version")
        maximum = manifest.get("max_version")
        if minimum and current < Version(str(minimum)):
            report.issues.append(
                DependencyIssue("tokenade", f">={minimum}", f"installed version is {current_version}")
            )
        if maximum and current > Version(str(maximum)):
            report.issues.append(
                DependencyIssue("tokenade", f"<={maximum}", f"installed version is {current_version}")
            )
    except InvalidVersion as exc:
        report.issues.append(DependencyIssue("tokenade", "version", f"invalid version: {exc}"))
    return report


def validate_runtime_dependency_manifest(manifest: Dict[str, Any]) -> List[str]:
    """Return syntax errors in runtime dependency declarations."""
    errors: List[str] = []
    runtime = manifest.get("runtime_dependencies", {})
    if not isinstance(runtime, dict):
        return ["runtime_dependencies must be an object"]
    for kind in ("python", "system"):
        values = runtime.get(kind, [])
        if not isinstance(values, list):
            errors.append(f"runtime_dependencies.{kind} must be a list")
            continue
        if len(values) > 50:
            errors.append(f"runtime_dependencies.{kind} has too many entries")
        for value in values:
            if not isinstance(value, str) or not value.strip():
                errors.append(f"runtime_dependencies.{kind} entries must be non-empty strings")
                continue
            if kind == "python":
                try:
                    Requirement(value)
                except Exception as exc:
                    errors.append(f"invalid Python requirement {value!r}: {exc}")
            elif "/" in value or "\\" in value:
                errors.append(f"system dependency must be an executable name: {value!r}")
    return errors
