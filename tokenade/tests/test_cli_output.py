"""
Tests for CLI OutputFormatter — colors, JSON mode, tables, progress.
"""
import json
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from tokenade.cli.output import OutputFormatter, create_formatter, _COLORS


# ---------------------------------------------------------------------------
# OutputFormatter tests
# ---------------------------------------------------------------------------

class TestOutputFormatterInit:
    def test_default_color_detection(self):
        formatter = OutputFormatter()
        # In test environment, stdout is not a tty
        assert formatter.use_color is False

    def test_json_mode_disables_color(self):
        formatter = OutputFormatter(json_mode=True)
        assert formatter.use_color is False
        assert formatter.json_mode is True

    def test_explicit_color(self):
        formatter = OutputFormatter(use_color=True)
        assert formatter.use_color is True

    def test_explicit_no_color(self):
        formatter = OutputFormatter(use_color=False)
        assert formatter.use_color is False


class TestOutputFormatterColor:
    def test_color_enabled(self):
        formatter = OutputFormatter(use_color=True)
        result = formatter._c("red", "hello")
        assert _COLORS["red"] in result
        assert "hello" in result
        assert _COLORS["reset"] in result

    def test_color_disabled(self):
        formatter = OutputFormatter(use_color=False)
        result = formatter._c("red", "hello")
        assert result == "hello"

    def test_unknown_color(self):
        formatter = OutputFormatter(use_color=True)
        result = formatter._c("nonexistent", "hello")
        assert "hello" in result


class TestOutputFormatterMessages:
    def test_success_no_json(self, capsys):
        formatter = OutputFormatter(use_color=False)
        formatter.success("done")
        output = capsys.readouterr().out
        assert "done" in output
        assert "[OK]" in output

    def test_error_no_json(self, capsys):
        formatter = OutputFormatter(use_color=False)
        formatter.error("failed")
        output = capsys.readouterr().out
        assert "failed" in output
        assert "[X]" in output

    def test_warning_no_json(self, capsys):
        formatter = OutputFormatter(use_color=False)
        formatter.warning("careful")
        output = capsys.readouterr().out
        assert "careful" in output
        assert "[WARN]" in output

    def test_info_no_json(self, capsys):
        formatter = OutputFormatter(use_color=False)
        formatter.info("fyi")
        output = capsys.readouterr().out
        assert "fyi" in output
        assert "[i]" in output

    def test_success_json(self):
        formatter = OutputFormatter(json_mode=True)
        formatter.success("done")
        result = formatter.flush_json()
        assert result is not None
        data = json.loads(result)
        assert data[0]["status"] == "success"
        assert data[0]["message"] == "done"

    def test_error_json(self):
        formatter = OutputFormatter(json_mode=True)
        formatter.error("failed")
        result = formatter.flush_json()
        data = json.loads(result)
        assert data[0]["status"] == "error"

    def test_warning_json(self):
        formatter = OutputFormatter(json_mode=True)
        formatter.warning("careful")
        result = formatter.flush_json()
        data = json.loads(result)
        assert data[0]["status"] == "warning"

    def test_info_json(self):
        formatter = OutputFormatter(json_mode=True)
        formatter.info("fyi")
        result = formatter.flush_json()
        data = json.loads(result)
        assert data[0]["status"] == "info"


class TestOutputFormatterHeader:
    def test_header_no_json(self, capsys):
        formatter = OutputFormatter(use_color=False)
        formatter.header("Title")
        output = capsys.readouterr().out
        assert "Title" in output
        assert "=" in output

    def test_header_json(self):
        formatter = OutputFormatter(json_mode=True)
        formatter.header("Title")
        result = formatter.flush_json()
        data = json.loads(result)
        assert data[0]["type"] == "header"
        assert data[0]["title"] == "Title"


class TestOutputFormatterTable:
    def test_table_no_json(self, capsys):
        formatter = OutputFormatter(use_color=False)
        formatter.table(["Name", "Value"], [["a", "1"], ["b", "2"]])
        output = capsys.readouterr().out
        assert "Name" in output
        assert "Value" in output
        assert "a" in output
        assert "2" in output

    def test_table_json(self):
        formatter = OutputFormatter(json_mode=True)
        formatter.table(["Name", "Value"], [["a", "1"]])
        result = formatter.flush_json()
        data = json.loads(result)
        assert data[0]["type"] == "table"
        assert data[0]["headers"] == ["Name", "Value"]
        assert data[0]["rows"] == [["a", "1"]]

    def test_table_empty_rows(self, capsys):
        formatter = OutputFormatter(use_color=False)
        formatter.table(["Name"], [])
        output = capsys.readouterr().out
        assert "Name" in output


class TestOutputFormatterProgress:
    def test_progress_no_json(self, capsys):
        formatter = OutputFormatter(use_color=False)
        formatter.progress(5, 10, "loading")
        output = capsys.readouterr().out
        assert "50%" in output

    def test_progress_json_silent(self):
        formatter = OutputFormatter(json_mode=True)
        formatter.progress(5, 10)
        result = formatter.flush_json()
        assert result is None  # progress doesn't output JSON


class TestOutputFormatterFlush:
    def test_flush_empty(self):
        formatter = OutputFormatter(json_mode=True)
        result = formatter.flush_json()
        assert result is None

    def test_flush_non_json_mode(self):
        formatter = OutputFormatter(json_mode=False)
        formatter.success("test")
        result = formatter.flush_json()
        assert result is None

    def test_flush_multiple(self):
        formatter = OutputFormatter(json_mode=True)
        formatter.success("one")
        formatter.error("two")
        result = formatter.flush_json()
        data = json.loads(result)
        assert len(data) == 2
        # After flush, pending is cleared
        result2 = formatter.flush_json()
        assert result2 is None


class TestOutputFormatterPrintJson:
    def test_print_json(self, capsys):
        formatter = OutputFormatter()
        formatter.print_json({"key": "value", "num": 42})
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["key"] == "value"
        assert data["num"] == 42


class TestCreateFormatter:
    def test_create_default(self):
        formatter = create_formatter()
        assert isinstance(formatter, OutputFormatter)

    def test_create_verbose(self):
        formatter = create_formatter(verbose=True)
        assert isinstance(formatter, OutputFormatter)

    def test_create_json(self):
        formatter = create_formatter(json_mode=True)
        assert formatter.json_mode is True
