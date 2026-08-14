"""Proxy provider plugin resolution and credential redaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from tokenade.core.integration.plugin_loader import PluginLoader
from tokenade.core.request_config import PluginRequest


class ProxyProviderError(RuntimeError):
    """Raised when a proxy provider cannot be resolved."""


@dataclass(frozen=True)
class ResolvedProxy:
    server: str
    username: Optional[str] = None
    password: Optional[str] = None
    provider: Optional[str] = None
    mode: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self, *, show_secrets: bool = False) -> Dict[str, Any]:
        data = {
            "server": self.server,
            "provider": self.provider,
            "mode": self.mode,
            "metadata": self.metadata or {},
        }
        if self.username is not None:
            data["username"] = self.username if show_secrets else _redact(self.username)
        if self.password is not None:
            data["password"] = self.password if show_secrets else "***"
        return {key: value for key, value in data.items() if value not in (None, {})}


class ProxyProviderResolver:
    """Resolve upstream proxy settings through proxy provider plugins."""

    def __init__(self, loader: Optional[PluginLoader] = None):
        self.loader = loader or PluginLoader()

    def resolve(
        self,
        plugin: PluginRequest,
        *,
        session_metadata: Optional[Dict[str, Any]] = None,
        source_network: Optional[Dict[str, Any]] = None,
    ) -> ResolvedProxy:
        loaded = self.loader.load_by_name(plugin.name)
        if loaded is None or loaded.instance is None:
            raise ProxyProviderError(_missing_provider_message(plugin.name))
        if not loaded.is_active:
            raise ProxyProviderError(
                f"proxy provider plugin '{plugin.name}' is not active "
                f"(state: {loaded.state.value})"
            )

        try:
            operation = self._operation(loaded.instance)
            result = operation(
                role_config=plugin.role_config("proxy_provider"),
                config=plugin.config,
                session_metadata=session_metadata or {},
                source_network=source_network or {},
            )
            return normalize_proxy_result(result, provider=plugin.name, mode=plugin.role_config("proxy_provider").get("mode"))
        finally:
            unload = getattr(self.loader, "unload", None)
            if callable(unload):
                unload(plugin.name)

    def _operation(self, instance):
        for name in ("resolve_proxy", "get_proxy", "provide_proxy"):
            operation = getattr(instance, name, None)
            if callable(operation):
                return operation
        raise ProxyProviderError("proxy provider plugin must define resolve_proxy(), get_proxy(), or provide_proxy()")


def normalize_proxy_result(result: Any, *, provider: Optional[str] = None, mode: Optional[str] = None) -> ResolvedProxy:
    """Normalize provider plugin output into Tokenade's internal proxy shape."""
    if isinstance(result, ResolvedProxy):
        return result
    if not isinstance(result, dict):
        raise ProxyProviderError("proxy provider result must be an object")

    server = result.get("server") or result.get("url") or result.get("proxy")
    if not isinstance(server, str) or not server.strip():
        raise ProxyProviderError("proxy provider result.server is required")

    return ResolvedProxy(
        server=server.strip(),
        username=_optional_string(result.get("username") or result.get("user")),
        password=_optional_string(result.get("password") or result.get("pass")),
        provider=_optional_string(result.get("provider")) or provider,
        mode=_optional_string(result.get("mode")) or mode,
        metadata=result.get("metadata") if isinstance(result.get("metadata"), dict) else None,
    )


def _optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _redact(value: str) -> str:
    if len(value) <= 2:
        return "***"
    return value[:2] + "***"


def _missing_provider_message(name: str) -> str:
    return "\n".join([
        f"Required plugin not installed: {name}",
        "",
        "Try:",
        f"  tokenade plugin install {name}",
        f"  tokenade plugin install {name} --registry <registry-name-or-url>",
    ])
