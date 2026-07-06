"""
Tokenade Plugin API v1.0

Standard types and interfaces for the Tokenade plugin system.
All plugins should use these types for consistent behavior.

Usage:
    from tokenade.plugin.api import API_VERSION, PluginResult, PluginConfig

    class MyPlugin:
        API_VERSION = "1.0.0"
        ...
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Current Plugin API version
# Bump this when making breaking changes to plugin interfaces.
# Plugins with mismatched API_VERSION will fail to load.
API_VERSION = "1.0.0"


@dataclass
class PluginResult:
    """Standard result type for all plugin operations.

    All plugin methods should return PluginResult instead of
    plain dict/bool. This ensures consistent error handling.

    Usage:
        return PluginResult(success=True, data={"session": updated})
        return PluginResult(success=False, error="Token expired")
    """
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "warnings": self.warnings,
            "duration_ms": self.duration_ms,
        }


@dataclass
class PluginMetadata:
    """Standard plugin metadata.

    Plugins expose this via get_metadata().
    """
    name: str
    version: str
    api_version: str
    author: str
    description: str
    category: str = ""
    tags: List[str] = field(default_factory=list)
    icon: str = "📦"
    min_tokenade_version: str = "6.0.0"
    dependencies: List[str] = field(default_factory=list)


@dataclass
class PluginConfigSchema:
    """Schema definition for a plugin config field."""
    name: str
    type: str  # "string", "int", "bool", "float"
    required: bool = False
    default: Any = None
    description: str = ""


class PluginConfig:
    """Standard plugin configuration with schema validation.

    Plugins declare their config schema, and the loader validates
    the actual config values against it.

    Usage:
        schema = {
            "api_key": {"type": "string", "required": True, "description": "API key"},
            "timeout": {"type": "int", "required": False, "default": 30},
        }
        config = PluginConfig(schema=schema, values={"api_key": "xxx"})
        errors = config.validate()
    """

    def __init__(
        self,
        schema: Optional[Dict[str, Any]] = None,
        values: Optional[Dict[str, Any]] = None,
    ):
        self._schema = schema or {}
        self._values = values or {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value."""
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a config value."""
        self._values[key] = value

    def validate(self) -> List[str]:
        """Validate config values against schema.

        Returns:
            List of error messages (empty if valid).
        """
        errors = []
        for key, spec in self._schema.items():
            if spec.get("required") and key not in self._values:
                errors.append(f"Missing required config: {key}")
            elif key in self._values:
                val = self._values[key]
                expected_type = spec.get("type", "string")
                if expected_type == "int" and not isinstance(val, int):
                    errors.append(f"Config '{key}' must be int, got {type(val).__name__}")
                elif expected_type == "bool" and not isinstance(val, bool):
                    errors.append(f"Config '{key}' must be bool, got {type(val).__name__}")
                elif expected_type == "float" and not isinstance(val, (int, float)):
                    errors.append(f"Config '{key}' must be float, got {type(val).__name__}")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": self._schema, "values": self._values}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginConfig':
        return cls(
            schema=data.get("schema", {}),
            values=data.get("values", {}),
        )
