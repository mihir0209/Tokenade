"""Tests for structured logging (Phase 36)."""
import json
import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tokenade.core.logging.structured import (
    StructuredFormatter, HumanFormatter, LogManager, get_tokenade_logger,
)


class TestStructuredFormatter:

    def test_basic_format(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="tokenade.test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="hello", args=(), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "hello"
        assert data["level"] == "INFO"
        assert data["logger"] == "tokenade.test"

    def test_format_with_extras(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="tokenade.test", level=logging.WARNING, pathname="t.py",
            lineno=1, msg="warn", args=(), exc_info=None,
        )
        record.custom_field = "custom_value"
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "WARNING"
        assert "extras" in data
        assert data["extras"]["custom_field"] == "custom_value"

    def test_format_with_exception(self):
        formatter = StructuredFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="tokenade.test", level=logging.ERROR, pathname="t.py",
            lineno=1, msg="error", args=(), exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert data["exception"]["type"] == "ValueError"
        assert "test error" in data["exception"]["message"]

    def test_format_fields_present(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="tokenade.core.browser", level=logging.DEBUG, pathname="browser.py",
            lineno=42, msg="debug msg", args=(), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "timestamp" in data
        assert data["level"] == "DEBUG"
        assert data["logger"] == "tokenade.core.browser"
        assert data["module"] == "browser"
        assert data["function"] is None or data["function"] == ""
        assert data["line"] == 42

    def test_format_args_interpolation(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="tokenade.test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="count: %d", args=(5,), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "count: 5"


class TestHumanFormatter:

    def test_basic_format(self):
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="tokenade.test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="hello", args=(), exc_info=None,
        )
        output = formatter.format(record)
        assert "INFO" in output
        assert "hello" in output

    def test_color_codes(self):
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="tokenade.test", level=logging.ERROR, pathname="t.py",
            lineno=1, msg="err", args=(), exc_info=None,
        )
        output = formatter.format(record)
        assert "\033[31m" in output

    def test_short_name(self):
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="tokenade.core.browser.cdp", level=logging.INFO,
            pathname="t.py", lineno=1, msg="msg", args=(), exc_info=None,
        )
        output = formatter.format(record)
        assert "[cdp]" in output

    def test_exception_format(self):
        formatter = HumanFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="tokenade.test", level=logging.ERROR, pathname="t.py",
            lineno=1, msg="fail", args=(), exc_info=exc_info,
        )
        output = formatter.format(record)
        assert "RuntimeError" in output


class TestLogManager:

    def setup_method(self):
        LogManager.reset()

    def teardown_method(self):
        LogManager.reset()

    def test_setup_creates_log_dir(self, tmp_path):
        log_dir = str(tmp_path / "test_logs")
        LogManager.setup(log_dir=log_dir)
        assert Path(log_dir).exists()
        LogManager.reset()

    def test_setup_idempotent(self, tmp_path):
        log_dir = str(tmp_path / "test_logs2")
        LogManager.setup(log_dir=log_dir)
        LogManager.setup(log_dir=str(tmp_path / "other"))
        assert LogManager._log_dir == Path(log_dir)

    def test_get_log_dir_default(self):
        from tokenade.core.logging.structured import DEFAULT_LOG_DIR
        assert LogManager.get_log_dir() == DEFAULT_LOG_DIR

    def test_get_log_dir_custom(self, tmp_path):
        log_dir = str(tmp_path / "custom_logs")
        LogManager.setup(log_dir=log_dir)
        assert LogManager.get_log_dir() == Path(log_dir)

    def test_read_recent_no_file(self, tmp_path):
        LogManager._log_dir = tmp_path
        result = LogManager.read_recent()
        assert result == []

    def test_read_recent(self, tmp_path):
        log_file = tmp_path / "tokenade.log"
        lines = ["line1\n", "line2\n", "line3\n"]
        log_file.write_text("".join(lines))
        LogManager._log_dir = tmp_path
        result = LogManager.read_recent(lines=2)
        assert len(result) == 2
        assert "line2" in result[0]
        assert "line3" in result[1]

    def test_read_recent_custom_file(self, tmp_path):
        custom = tmp_path / "custom.log"
        custom.write_text("custom_line1\ncustom_line2\n")
        result = LogManager.read_recent(log_file=str(custom))
        assert len(result) == 2

    def test_search(self, tmp_path):
        log_file = tmp_path / "tokenade.log"
        log_file.write_text('{"level":"ERROR","message":"fail"}\n{"level":"INFO","message":"ok"}\n')
        LogManager._log_dir = tmp_path
        results = LogManager.search("ERROR")
        assert len(results) == 1
        assert "fail" in results[0]

    def test_search_no_file(self, tmp_path):
        LogManager._log_dir = tmp_path
        results = LogManager.search("anything")
        assert results == []

    def test_get_log_files_empty(self, tmp_path):
        LogManager._log_dir = tmp_path
        files = LogManager.get_log_files()
        assert files == []

    def test_get_log_files(self, tmp_path):
        LogManager._log_dir = tmp_path
        (tmp_path / "tokenade.log").write_text("data")
        (tmp_path / "tokenade.log.1").write_text("old")
        files = LogManager.get_log_files()
        assert len(files) == 2
        assert files[0]["name"] == "tokenade.log"
        assert "size_bytes" in files[0]
        assert "modified" in files[0]

    def test_cleanup_old_logs(self, tmp_path):
        LogManager._log_dir = tmp_path
        old_file = tmp_path / "tokenade.log.5"
        old_file.write_text("old")
        import os
        old_mtime = 0
        os.utime(str(old_file), (old_mtime, old_mtime))
        removed = LogManager.cleanup_old_logs(retention_days=1)
        assert removed == 1
        assert not old_file.exists()

    def test_cleanup_keeps_recent(self, tmp_path):
        LogManager._log_dir = tmp_path
        recent_file = tmp_path / "tokenade.log"
        recent_file.write_text("recent")
        removed = LogManager.cleanup_old_logs(retention_days=365)
        assert removed == 0
        assert recent_file.exists()

    def test_reset(self, tmp_path):
        LogManager.setup(log_dir=str(tmp_path / "logs"))
        assert LogManager._initialized is True
        LogManager.reset()
        assert LogManager._initialized is False
        assert LogManager._log_dir is None


class TestGetTokenadeLogger:

    def test_returns_logger(self):
        log = get_tokenade_logger("tokenade.test.module")
        assert isinstance(log, logging.Logger)
        assert log.name == "tokenade.test.module"

    def test_same_name_returns_same_logger(self):
        log1 = get_tokenade_logger("tokenade.test.same")
        log2 = get_tokenade_logger("tokenade.test.same")
        assert log1 is log2
