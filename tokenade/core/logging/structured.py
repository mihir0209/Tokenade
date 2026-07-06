"""
Structured logging for Tokenade.

Provides JSON-formatted log output, log rotation, and structured fields.
"""

import json
import logging
import logging.handlers

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_LOG_DIR = Path.home() / ".tokenade" / "logs"
MAX_LOG_SIZE_MB = 10
LOG_BACKUP_COUNT = 7


class StructuredFormatter(logging.Formatter):
    """JSON-formatted log formatter for machine-parseable output."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        extras = {}
        skip_keys = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())
        skip_keys.update({"message", "msg", "args", "taskName"})
        for key in record.__dict__:
            if key not in skip_keys:
                extras[key] = getattr(record, key, None)
        if extras:
            log_entry["extras"] = extras

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter with colors for terminal output."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[1;31m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        level = f"{color}{record.levelname:<8}{self.RESET}"
        name = record.name.split(".")[-1]
        msg = record.getMessage()
        line = f"{timestamp} {level} [{name}] {msg}"
        if record.exc_info and record.exc_info[0]:
            line += f"\n{traceback.format_exception(*record.exc_info)}"
        return line


class LogManager:
    """Centralized log management for Tokenade."""

    _initialized = False
    _log_dir: Optional[Path] = None

    @classmethod
    def setup(cls, level: str = "INFO", log_dir: Optional[str] = None,
              json_output: bool = False, max_size_mb: int = MAX_LOG_SIZE_MB,
              backup_count: int = LOG_BACKUP_COUNT):
        if cls._initialized:
            return

        cls._log_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        cls._log_dir.mkdir(parents=True, exist_ok=True)

        root_logger = logging.getLogger("tokenade")
        root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        root_logger.handlers.clear()

        log_file = cls._log_dir / "tokenade.log"
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_file),
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=backup_count,
        )
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stderr)
        if json_output:
            console_handler.setFormatter(StructuredFormatter())
        else:
            console_handler.setFormatter(HumanFormatter())
        root_logger.addHandler(console_handler)

        cls._initialized = True

    @classmethod
    def reset(cls):
        """Reset initialization state (for testing)."""
        cls._initialized = False
        cls._log_dir = None

    @classmethod
    def get_log_dir(cls) -> Path:
        return cls._log_dir or DEFAULT_LOG_DIR

    @classmethod
    def get_log_files(cls):
        log_dir = cls.get_log_dir()
        files = []
        for f in sorted(log_dir.glob("tokenade.log*")):
            files.append({
                "path": str(f),
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
        return files

    @classmethod
    def cleanup_old_logs(cls, retention_days: int = 7):
        log_dir = cls.get_log_dir()
        cutoff = datetime.now().timestamp() - (retention_days * 86400)
        removed = 0
        for f in log_dir.glob("tokenade.log*"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        return removed

    @classmethod
    def read_recent(cls, lines: int = 50, log_file: Optional[str] = None) -> list:
        if log_file:
            path = Path(log_file)
        else:
            path = cls.get_log_dir() / "tokenade.log"
        if not path.exists():
            return []
        try:
            content = path.read_text()
            log_lines = content.strip().split("\n")
            return log_lines[-lines:]
        except Exception:
            return []

    @classmethod
    def search(cls, query: str, log_file: Optional[str] = None) -> list:
        if log_file:
            path = Path(log_file)
        else:
            path = cls.get_log_dir() / "tokenade.log"
        if not path.exists():
            return []
        try:
            content = path.read_text()
            return [line for line in content.split("\n") if query in line]
        except Exception:
            return []


def get_tokenade_logger(name: str) -> logging.Logger:
    """Get a logger for a Tokenade module."""
    return logging.getLogger(name)
