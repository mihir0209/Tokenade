"""Nested request.json loading and validation for Tokenade operations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tokenade.core.integration.plugin_loader import PluginLoader


class RequestConfigError(ValueError):
    """Raised when a request.json file is malformed or cannot be satisfied."""


@dataclass
class PluginRequest:
    """One ordered plugin entry from request.json."""

    name: str
    required: bool = True
    roles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def role_config(self, role: str) -> Dict[str, Any]:
        data = self.roles.get(role) or {}
        return data if isinstance(data, dict) else {}


@dataclass
class RequestConfig:
    """Validated nested request.json envelope."""

    version: str
    operation: str
    plugins: List[PluginRequest] = field(default_factory=list)
    execution: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def stop_on_error(self) -> bool:
        value = self.execution.get("stop_on_error", True)
        return value if isinstance(value, bool) else True

    def plugins_for_role(self, role: str) -> List[PluginRequest]:
        return [plugin for plugin in self.plugins if role in plugin.roles]


def load_request_config(path: str | Path, *, validate_plugins: bool = True) -> RequestConfig:
    """Load and validate a nested Tokenade request file."""
    request_path = Path(path)
    try:
        with open(request_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RequestConfigError(f"invalid request file: {exc}") from exc

    config = parse_request_config(data)
    if validate_plugins:
        validate_required_plugins(config.plugins)
    return config


def parse_request_config(data: Dict[str, Any]) -> RequestConfig:
    """Validate a nested request object already loaded from JSON."""
    if not isinstance(data, dict):
        raise RequestConfigError("request must be a JSON object")

    operation = data.get("operation")
    if not isinstance(operation, str) or not operation.strip():
        raise RequestConfigError("request.operation is required")

    version = data.get("version", "1")
    if not isinstance(version, str) or not version.strip():
        raise RequestConfigError("request.version must be a string")

    raw_plugins = data.get("plugins", [])
    if not isinstance(raw_plugins, list):
        raise RequestConfigError("request.plugins must be an array")

    plugins = [_parse_plugin_entry(entry, index) for index, entry in enumerate(raw_plugins)]

    execution = data.get("execution", {})
    if not isinstance(execution, dict):
        raise RequestConfigError("request.execution must be an object")
    if "stop_on_error" in execution and not isinstance(execution["stop_on_error"], bool):
        raise RequestConfigError("request.execution.stop_on_error must be a boolean")

    return RequestConfig(
        version=version,
        operation=operation.strip(),
        plugins=plugins,
        execution=execution,
        raw=data,
    )


def validate_required_plugins(plugins: List[PluginRequest], *, loader: Optional[PluginLoader] = None) -> None:
    """Fail closed when request.json declares a missing required plugin."""
    plugin_loader = loader or PluginLoader()
    missing = [plugin.name for plugin in plugins if plugin.required and plugin_loader.get_manifest(plugin.name) is None]
    if missing:
        raise RequestConfigError(_missing_plugins_message(missing))


def _parse_plugin_entry(entry: Any, index: int) -> PluginRequest:
    if not isinstance(entry, dict):
        raise RequestConfigError(f"request.plugins[{index}] must be an object")

    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RequestConfigError(f"request.plugins[{index}].name is required")

    required = entry.get("required", True)
    if not isinstance(required, bool):
        raise RequestConfigError(f"request.plugins[{index}].required must be a boolean")

    roles = entry.get("roles", {})
    if not isinstance(roles, dict):
        raise RequestConfigError(f"request.plugins[{index}].roles must be an object")
    for role, role_config in roles.items():
        if not isinstance(role, str) or not role.strip():
            raise RequestConfigError(f"request.plugins[{index}].roles contains an invalid role")
        if not isinstance(role_config, dict):
            raise RequestConfigError(f"request.plugins[{index}].roles.{role} must be an object")

    config = entry.get("config", {})
    if not isinstance(config, dict):
        raise RequestConfigError(f"request.plugins[{index}].config must be an object")

    return PluginRequest(
        name=name.strip(),
        required=required,
        roles=roles,
        config=config,
        raw=entry,
    )


def _missing_plugins_message(names: List[str]) -> str:
    lines = []
    for name in names:
        lines.extend([
            f"Required plugin not installed: {name}",
            "",
            "Try:",
            f"  tokenade plugin install {name}",
            f"  tokenade plugin install {name} --registry <registry-name-or-url>",
        ])
    return "\n".join(lines)
