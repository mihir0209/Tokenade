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
API_VERSION = "1.1.0"


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
    type: str = "string"  # string, int, bool, float, list, dict
    required: bool = False
    default: Any = None
    description: str = ""
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None
    choices: Optional[List[Any]] = None
    env_var: Optional[str] = None


class PluginConfig:
    """Standard plugin configuration with schema validation.

    Plugins declare their config schema, and the loader validates
    the actual config values against it.

    Schema format (dict):
        {
            "api_key": {
                "type": "string", "required": True,
                "description": "API key",
                "env_var": "TOKENADE_API_KEY",
            },
            "timeout": {
                "type": "int", "default": 30,
                "min": 1, "max": 300,
            },
            "mode": {
                "type": "string", "choices": ["fast", "slow"],
                "default": "fast",
            },
            "pattern_match": {
                "type": "string", "pattern": "^[a-z]+$",
            },
        }

    Usage:
        schema = {...}
        config = PluginConfig(schema=schema, values={"api_key": "xxx"})
        errors = config.validate()
    """

    VALID_TYPES = {"string", "int", "bool", "float", "list", "dict"}

    def __init__(
        self,
        schema: Optional[Dict[str, Any]] = None,
        values: Optional[Dict[str, Any]] = None,
    ):
        self._schema = schema or {}
        self._values = self._apply_env_vars(dict(values or {}))

    def _apply_env_vars(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Apply env var overrides from schema if env var is set."""
        import os

        for key, spec in self._schema.items():
            env_var = spec.get("env_var")
            if env_var and env_var in os.environ:
                env_val = os.environ[env_var]
                # Convert env string to the right type
                expected_type = spec.get("type", "string")
                try:
                    if expected_type == "int":
                        values[key] = int(env_val)
                    elif expected_type == "float":
                        values[key] = float(env_val)
                    elif expected_type == "bool":
                        values[key] = env_val.lower() in ("1", "true", "yes")
                    else:
                        values[key] = env_val
                except ValueError:
                    values[key] = env_val  # keep as string
        return values

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value.

        Falls back to schema default if value not set.
        """
        if key in self._values:
            return self._values[key]
        # Check schema default
        spec = self._schema.get(key, {})
        return spec.get("default", default)

    def set(self, key: str, value: Any) -> None:
        """Set a config value."""
        self._values[key] = value

    def validate(self) -> List[str]:
        """Validate config values against schema.

        Checks:
        - Required fields present
        - Type matches
        - min/max constraints (int/float)
        - pattern constraints (string)
        - choices constraint
        - list/dict types

        Returns:
            List of error messages (empty if valid).
        """
        import re

        errors = []
        for key, spec in self._schema.items():
            expected_type = spec.get("type", "string")
            required = spec.get("required", False)
            default = spec.get("default")

            # Get value (with default fallback)
            value = self._values.get(key, default)

            # Check required
            if required and value is None and key not in self._values:
                errors.append(f"Missing required config: {key}")
                continue

            # Skip validation if value is None and not required
            if value is None and not required:
                continue

            # Type checking
            if expected_type == "int" and not isinstance(value, int):
                errors.append(f"Config '{key}' must be int, got {type(value).__name__}")
            elif expected_type == "bool" and not isinstance(value, bool):
                errors.append(f"Config '{key}' must be bool, got {type(value).__name__}")
            elif expected_type == "float" and not isinstance(value, (int, float)):
                errors.append(f"Config '{key}' must be float, got {type(value).__name__}")
            elif expected_type == "string" and not isinstance(value, str):
                errors.append(f"Config '{key}' must be string, got {type(value).__name__}")
            elif expected_type == "list" and not isinstance(value, list):
                errors.append(f"Config '{key}' must be list, got {type(value).__name__}")
            elif expected_type == "dict" and not isinstance(value, dict):
                errors.append(f"Config '{key}' must be dict, got {type(value).__name__}")

            # Min/max constraints (int/float)
            if expected_type in ("int", "float") and isinstance(value, (int, float)):
                min_val = spec.get("min")
                max_val = spec.get("max")
                if min_val is not None and value < min_val:
                    errors.append(
                        f"Config '{key}' value {value} is below min {min_val}"
                    )
                if max_val is not None and value > max_val:
                    errors.append(
                        f"Config '{key}' value {value} exceeds max {max_val}"
                    )

            # Pattern constraint (string)
            if expected_type == "string" and isinstance(value, str):
                pattern = spec.get("pattern")
                if pattern:
                    try:
                        if not re.match(pattern, value):
                            errors.append(
                                f"Config '{key}' value '{value}' doesn't match pattern {pattern}"
                            )
                    except re.error:
                        pass  # invalid pattern — skip

            # Choices constraint
            choices = spec.get("choices")
            if choices and value not in choices:
                errors.append(
                    f"Config '{key}' value '{value}' not in choices {choices}"
                )

        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": self._schema, "values": self._values}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginConfig':
        return cls(
            schema=data.get("schema", {}),
            values=data.get("values", {}),
        )
