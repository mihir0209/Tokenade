"""Tokenade configuration file support."""
import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_DIR = Path.home() / ".tokenade"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


class TokenadeConfig:
    def __init__(self, config_file: Path = DEFAULT_CONFIG_FILE):
        self.config_file = config_file
        self._defaults = {
            "browser": "chrome",
            "output_format": "tokenade",
            "proxy_port": 9222,
            "proxy_host": "127.0.0.1",
            "sessions_dir": "~/.tokenade/sessions",
            "auto_refresh": False,
            "source_browser": None,
        }
        self._config = self._load()

    def _load(self) -> dict:
        if self.config_file.exists():
            with open(self.config_file) as f:
                return {**self._defaults, **json.load(f)}
        return self._defaults.copy()

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        self._config[key] = value
        self._save()

    def _save(self):
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(self._config, f, indent=2)

    def delete(self, key: str):
        self._config.pop(key, None)
        self._save()

    def list_all(self) -> dict:
        return self._config.copy()
