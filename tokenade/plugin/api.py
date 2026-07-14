"""
Tokenade Plugin API v1.3

Standard types and interfaces for the Tokenade plugin system.
All plugins should use these types for consistent behavior.

Usage:
    from tokenade.plugin.api import API_VERSION, PluginResult, PluginConfig

    class MyPlugin:
        API_VERSION = "1.3.0"
        ...
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Current Plugin API version
# Bump this when making breaking changes to plugin interfaces.
# Plugins with mismatched API_VERSION will fail to load.
API_VERSION = "1.3.0"

RUN_METHODS = frozenset({"process", "run", "refresh_session"})
RUN_ARGUMENT_TYPES = frozenset({
    "string", "path", "int", "float", "bool", "list", "object",
})


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


class PluginRunErrorCode(str, Enum):
    """Stable error codes used by the external plugin runner."""

    MANIFEST_ERROR = "PLUGIN_MANIFEST_ERROR"
    ARGUMENT_ERROR = "PLUGIN_ARGUMENT_ERROR"
    METHOD_ERROR = "PLUGIN_METHOD_ERROR"
    LOAD_ERROR = "PLUGIN_LOAD_ERROR"
    INVOCATION_ERROR = "PLUGIN_INVOCATION_ERROR"
    PLUGIN_FAILURE = "PLUGIN_FAILURE"


@dataclass
class PluginRunError:
    """Serializable error returned by an external plugin invocation."""

    code: PluginRunErrorCode
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"code": self.code.value, "message": self.message}


@dataclass
class PluginRunEnvelope:
    """Machine-readable result envelope for ``tokenade run``."""

    success: bool
    plugin: str
    method: str
    data: Any = None
    error: Optional[PluginRunError] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "plugin": self.plugin,
            "method": self.method,
            "data": self.data,
            "error": self.error.to_dict() if self.error else None,
        }


@dataclass
class PluginRunArgument:
    """One declared input field for an executable plugin method."""

    name: str
    type: str = "string"
    required: bool = False
    default: Any = None


@dataclass
class PluginRunMethod:
    """Manifest declaration for one executable plugin method."""

    name: str
    arguments: Dict[str, PluginRunArgument] = field(default_factory=dict)


@dataclass
class PluginRunSpec:
    """Validated optional external execution section from a plugin manifest."""

    enabled: bool
    default_method: str
    methods: Dict[str, PluginRunMethod]


def parse_plugin_run_spec(manifest: Dict[str, Any]) -> Optional[PluginRunSpec]:
    """Validate and parse the optional ``run`` manifest section.

    A missing section means the plugin is internal-only. Malformed present
    sections raise ``ValueError`` so the loader/runner can report a precise
    manifest error.
    """
    raw = manifest.get("run")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("run must be an object")

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("run.enabled must be a boolean")

    raw_methods = raw.get("methods", {})
    if not isinstance(raw_methods, dict) or not raw_methods:
        raise ValueError("run.methods must be a non-empty object")

    methods: Dict[str, PluginRunMethod] = {}
    for method_name, method_data in raw_methods.items():
        if method_name not in RUN_METHODS:
            raise ValueError(f"unsupported run method: {method_name}")
        if not isinstance(method_data, dict):
            raise ValueError(f"run.methods.{method_name} must be an object")

        raw_arguments = method_data.get("arguments", {})
        if not isinstance(raw_arguments, dict):
            raise ValueError(f"run.methods.{method_name}.arguments must be an object")

        arguments: Dict[str, PluginRunArgument] = {}
        for name, definition in raw_arguments.items():
            if not isinstance(name, str) or not name.isidentifier():
                raise ValueError(f"invalid argument name: {name}")
            if not isinstance(definition, dict):
                raise ValueError(f"argument {name} must be an object")
            arg_type = definition.get("type", "string")
            if arg_type not in RUN_ARGUMENT_TYPES:
                raise ValueError(f"unsupported argument type for {name}: {arg_type}")
            required = definition.get("required", False)
            if not isinstance(required, bool):
                raise ValueError(f"argument {name}.required must be a boolean")
            arguments[name] = PluginRunArgument(
                name=name,
                type=arg_type,
                required=required,
                default=definition.get("default"),
            )
        methods[method_name] = PluginRunMethod(method_name, arguments)

    default_method = raw.get("default_method")
    if default_method is None:
        default_method = next(iter(methods))
    if default_method not in methods:
        raise ValueError(f"run.default_method is not declared: {default_method}")

    if enabled and not default_method:
        raise ValueError("enabled run section requires a default method")
    return PluginRunSpec(enabled, default_method, methods)


def validate_plugin_run_input(
    method: PluginRunMethod,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate and coerce a flat request according to a method schema."""
    if not isinstance(request, dict):
        raise ValueError("input must be a JSON object")

    unknown = sorted(set(request) - set(method.arguments))
    if unknown:
        raise ValueError(f"unknown arguments: {', '.join(unknown)}")

    result: Dict[str, Any] = {}
    for name, argument in method.arguments.items():
        if name not in request:
            if argument.required:
                raise ValueError(f"missing required argument: {name}")
            result[name] = argument.default
            continue
        result[name] = _coerce_plugin_run_value(name, request[name], argument.type)
    return result


def _coerce_plugin_run_value(name: str, value: Any, value_type: str) -> Any:
    """Coerce one JSON value or raise a schema error."""
    if value_type in ("string", "path"):
        if not isinstance(value, str):
            raise ValueError(f"argument {name} must be a {value_type}")
        return value
    if value_type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"argument {name} must be an int")
        return value
    if value_type == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"argument {name} must be a float")
        return float(value)
    if value_type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"argument {name} must be a bool")
        return value
    if value_type == "list":
        if not isinstance(value, list):
            raise ValueError(f"argument {name} must be a list")
        return value
    if value_type == "object":
        if not isinstance(value, dict):
            raise ValueError(f"argument {name} must be an object")
        return value
    raise ValueError(f"unsupported argument type for {name}: {value_type}")


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
