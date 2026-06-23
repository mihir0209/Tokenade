"""
Configuration - Load user preferences from ~/.tokenade/config.json.

Config file location: ~/.tokenade/config.json

Supported options:
- default_browser: Default browser to export from (e.g., "brave", "firefox")
- default_profile: Default browser profile name
- stealth_level: Default stealth level ("basic", "advanced", "maximum")
- visible: Show browser window by default (true/false)
- auto_validate: Auto-validate sessions after export (true/false)
- output_dir: Default output directory for exported sessions
- proxy_host: Default proxy host (local CDP proxy)
- proxy_port: Default proxy port (local CDP proxy)
- upstream_proxy: Upstream proxy URL (e.g. "socks5://user:pass@host:port")
- upstream_proxy_file: Path to proxy list file for rotation
- upstream_proxy_rotate: Enable proxy rotation (true/false)
- upstream_proxy_strategy: Rotation strategy ("round-robin", "random", "health-weighted", "sticky")
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".tokenade"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"

DEFAULTS = {
    "default_browser": None,
    "default_profile": None,
    "stealth_level": "maximum",
    "visible": False,
    "auto_validate": True,
    "output_dir": None,
    "proxy_host": "127.0.0.1",
    "proxy_port": 9223,
    "encrypt_by_default": False,
    "encryption_key_file": None,
    "encryption_password": None,
    "upstream_proxy": None,
    "upstream_proxy_file": None,
    "upstream_proxy_rotate": False,
    "upstream_proxy_strategy": "health-weighted",
}


class TokenadeConfig:
    """Load and manage user configuration from ~/.tokenade/config.json."""

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_FILE
        self._config = {}
        self._load()

    def _load(self):
        """Load config from file."""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                logger.debug(f"Loaded config from {self._config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config from {self._config_path}: {e}")
                self._config = {}
        else:
            self._config = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value. Falls back to defaults, then to provided default."""
        if key in self._config:
            return self._config[key]
        if key in DEFAULTS:
            return DEFAULTS[key]
        return default

    def set(self, key: str, value: Any):
        """Set a config value in memory (call save() to persist)."""
        self._config[key] = value

    def save(self):
        """Save current config to file."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
            logger.info(f"Config saved to {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    @property
    def config_path(self) -> str:
        return str(self._config_path)

    def __repr__(self):
        return f"TokenadeConfig({self._config})"


def load_config(config_path: Optional[str] = None) -> TokenadeConfig:
    """Convenience function to load config."""
    return TokenadeConfig(config_path)
