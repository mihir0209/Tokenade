"""White-box tests for plugin_testing.py — exercises every branch/path."""
import json

import pytest

from tokenade.core.integration.plugin_testing import (
    PluginTestRunner,
    PluginTestResult,
    PluginTestSuite,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plugin_dir(base, name, manifest=None, code="", *,
                     valid_handler=True):
    """Create a plugin directory with manifest and code."""
    d = base / name
    d.mkdir(exist_ok=True)
    if manifest is None:
        manifest = {
            "name": name, "version": "1.0.0", "type": "handler",
            "entry_point": "plugin.py", "description": f"Test {name}",
        }
    (d / "plugin.json").write_text(json.dumps(manifest))
    if code:
        (d / "plugin.py").write_text(code)
    return d


HANDLER_CODE = """\
from tokenade.plugin.base import SiteHandlerPlugin

class TestHandler(SiteHandlerPlugin):
    name = "test"
    version = "1.0.0"
    description = "test handler"
    domains = []
    def can_handle(self, url): return False
    def extract_session(self, ctx, url):
        from tokenade.plugin.api import PluginResult
        return PluginResult(success=True)
    def inject_session(self, ctx, session):
        from tokenade.plugin.api import PluginResult
        return PluginResult(success=True)
"""

EXPORT_CODE = """\
from tokenade.plugin.base import ExportFormatPlugin

class TestExport(ExportFormatPlugin):
    name = "test"
    version = "1.0.0"
    description = "test export"
    def get_format_name(self): return "test"
    def export(self, session, output_path): return output_path
"""

VALIDATOR_CODE = """\
from tokenade.plugin.base import SessionValidatorPlugin

class TestValidator(SessionValidatorPlugin):
    name = "test"
    version = "1.0.0"
    description = "test validator"
    def validate(self, session): return True
    def get_validation_rules(self): return {}
"""


@pytest.fixture
def runner(tmp_path):
    return PluginTestRunner(plugins_dir=tmp_path)


@pytest.fixture
def good_handler(tmp_path):
    _make_plugin_dir(tmp_path, "good_handler", code=HANDLER_CODE,
                     manifest={"name": "good_handler", "version": "1.0.0",
                               "type": "handler", "entry_point": "plugin.py",
                               "description": "A good handler",
                               "entry_class": "TestHandler"})
    return tmp_path


# ===================================================================
# PluginTestSuite properties  (lines 26-50)  — 5 branches
# ===================================================================

class TestPluginTestSuite:
    def test_empty_results(self):
        suite = PluginTestSuite(plugin_name="empty")
        assert suite.passed is True  # vacuous truth
        assert suite.total == 0
        assert suite.passed_count == 0
        assert suite.failed_count == 0
        assert "PASS" in suite.summary()
        assert "0/0" in suite.summary()

    def test_all_pass(self):
        suite = PluginTestSuite(plugin_name="a", results=[
            PluginTestResult("t1", True), PluginTestResult("t2", True),
        ])
        assert suite.passed is True
        assert suite.total == 2
        assert suite.passed_count == 2
        assert suite.failed_count == 0
        assert "PASS" in suite.summary()

    def test_mixed(self):
        suite = PluginTestSuite(plugin_name="b", results=[
            PluginTestResult("t1", True), PluginTestResult("t2", False, "bad"),
        ])
        assert suite.passed is False
        assert suite.total == 2
        assert suite.passed_count == 1
        assert suite.failed_count == 1
        assert "FAIL" in suite.summary()

    def test_summary_format(self):
        suite = PluginTestSuite(plugin_name="x", results=[
            PluginTestResult("t1", True),
        ])
        s = suite.summary()
        assert s == "x: PASS (1/1)"

    def test_summary_fail_format(self):
        suite = PluginTestSuite(plugin_name="x", results=[
            PluginTestResult("t1", True), PluginTestResult("t2", False),
        ])
        s = suite.summary()
        assert s == "x: FAIL (1/2)"


# ===================================================================
# _test_manifest_exists  (lines 75-83)  — 2 branches
# ===================================================================

class TestManifestExists:
    def test_exists(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "myplug")
        result = runner._test_manifest_exists("myplug")
        assert result.passed is True
        assert result.test_name == "manifest_exists"

    def test_missing(self, runner, tmp_path):
        (tmp_path / "noplugin").mkdir()
        result = runner._test_manifest_exists("noplugin")
        assert result.passed is False
        assert "Missing" in result.message


# ===================================================================
# _test_manifest_valid  (lines 85-122)  — 8 branches
# ===================================================================

class TestManifestValid:
    def test_no_manifest(self, runner, tmp_path):
        (tmp_path / "x").mkdir()
        result = runner._test_manifest_valid("x")
        assert result.passed is False
        assert "No manifest" in result.message

    def test_valid_manifest(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "v")
        result = runner._test_manifest_valid("v")
        assert result.passed is True

    def test_missing_required_fields(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "incomplete", manifest={"name": "incomplete"})
        result = runner._test_manifest_valid("incomplete")
        assert result.passed is False
        assert "Missing fields" in result.message

    def test_invalid_type(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "badtype",
                         manifest={"name": "badtype", "version": "1.0",
                                   "type": "invalid_xyz", "entry_point": "p.py"})
        result = runner._test_manifest_valid("badtype")
        assert result.passed is False
        assert "Invalid type" in result.message

    def test_vanity_metrics(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "vanity",
                         manifest={"name": "vanity", "version": "1.0",
                                   "type": "handler", "entry_point": "p.py",
                                   "downloads": 999})
        result = runner._test_manifest_valid("vanity")
        assert result.passed is False
        assert "Vanity" in result.message

    def test_json_error(self, runner, tmp_path):
        d = tmp_path / "badjson"
        d.mkdir()
        (d / "plugin.json").write_text("{bad json!!!")
        result = runner._test_manifest_valid("badjson")
        assert result.passed is False

    def test_os_error(self, runner, tmp_path, monkeypatch):
        _make_plugin_dir(tmp_path, "oserr")
        real_open = open

        def fake_open(path, *a, **kw):
            if "plugin.json" in str(path):
                raise OSError("disk full")
            return real_open(path, *a, **kw)
        monkeypatch.setattr("builtins.open", fake_open)
        result = runner._test_manifest_valid("oserr")
        assert result.passed is False
        assert "disk full" in result.message

    def test_vanity_rating(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "vr",
                         manifest={"name": "vr", "version": "1.0",
                                   "type": "handler", "entry_point": "p.py",
                                   "rating": 5.0})
        result = runner._test_manifest_valid("vr")
        assert result.passed is False
        assert "Vanity" in result.message


# ===================================================================
# _test_entry_point_exists  (lines 124-142)  — 4 branches
# ===================================================================

class TestEntryPointExists:
    def test_no_manifest(self, runner, tmp_path):
        (tmp_path / "no").mkdir()
        result = runner._test_entry_point_exists("no")
        assert result.passed is False

    def test_exists(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "ep", code="pass")
        result = runner._test_entry_point_exists("ep")
        assert result.passed is True

    def test_missing(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "ep2")  # no plugin.py
        result = runner._test_entry_point_exists("ep2")
        assert result.passed is False
        assert "Missing" in result.message

    def test_json_error(self, runner, tmp_path, monkeypatch):
        d = tmp_path / "ep3"
        d.mkdir()
        (d / "plugin.json").write_text("not json")
        result = runner._test_entry_point_exists("ep3")
        assert result.passed is False


# ===================================================================
# _test_entry_class_importable  (lines 144-170)  — 5 branches
# ===================================================================

class TestEntryClassImportable:
    def test_no_manifest(self, runner, tmp_path):
        (tmp_path / "nc").mkdir()
        result = runner._test_entry_class_importable("nc")
        assert result.passed is False

    def test_class_found(self, runner, good_handler):
        result = runner._test_entry_class_importable("good_handler")
        assert result.passed is True

    def test_class_not_found(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "bad_class",
                         manifest={"name": "bad_class", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py",
                                   "entry_class": "NonexistentClass"},
                         code="class Foo: pass")
        result = runner._test_entry_class_importable("bad_class")
        assert result.passed is False
        assert "not found" in result.message.lower()

    def test_no_entry_class(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "noec",
                         manifest={"name": "noec", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py"},
                         code="pass")
        result = runner._test_entry_class_importable("noec")
        assert result.passed is True

    def test_import_error(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "import_err",
                         manifest={"name": "import_err", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py",
                                   "entry_class": "Foo"},
                         code="raise ImportError('broken')")
        result = runner._test_entry_class_importable("import_err")
        assert result.passed is False


# ===================================================================
# _test_plugin_instantiable  (lines 172-229)  — 7 branches
# ===================================================================

class TestPluginInstantiable:
    def test_no_manifest(self, runner, tmp_path):
        (tmp_path / "nim").mkdir()
        result = runner._test_plugin_instantiable("nim")
        assert result.passed is False

    def test_explicit_class_found(self, runner, good_handler):
        result = runner._test_plugin_instantiable("good_handler")
        assert result.passed is True

    def test_explicit_class_missing_falls_to_auto_discover(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "fall_auto",
                         manifest={"name": "fall_auto", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py",
                                   "entry_class": "NoSuchClass"},
                         code=HANDLER_CODE)
        # entry_class is invalid but auto-discover finds TestHandler
        result = runner._test_plugin_instantiable("fall_auto")
        assert result.passed is True

    def test_auto_discover_found(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "auto",
                         manifest={"name": "auto", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py"},
                         code=HANDLER_CODE)
        result = runner._test_plugin_instantiable("auto")
        assert result.passed is True

    def test_auto_discover_no_subclass(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "nosub",
                         manifest={"name": "nosub", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py"},
                         code="class NotAPlugin:\n    pass")
        result = runner._test_plugin_instantiable("nosub")
        assert result.passed is False
        assert "No instantiable" in result.message

    def test_instantiation_error(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "badinit",
                         manifest={"name": "badinit", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py",
                                   "entry_class": "BadInit"},
                         code="class BadInit:\n    def __init__(self):\n        raise RuntimeError('boom')")
        result = runner._test_plugin_instantiable("badinit")
        assert result.passed is False

    def test_import_error(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "imperr",
                         manifest={"name": "imperr", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py"})
        (tmp_path / "imperr" / "plugin.py").write_text("raise ImportError('x')")
        result = runner._test_plugin_instantiable("imperr")
        assert result.passed is False


# ===================================================================
# _test_plugin_metadata  (lines 231-256)  — 5 branches
# ===================================================================

class TestPluginMetadata:
    def test_no_manifest(self, runner, tmp_path):
        (tmp_path / "nm").mkdir()
        result = runner._test_plugin_metadata("nm")
        assert result.passed is False

    def test_all_valid(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "ok", manifest={
            "name": "ok", "version": "1.0", "description": "desc",
            "type": "handler", "entry_point": "p.py",
        })
        result = runner._test_plugin_metadata("ok")
        assert result.passed is True

    def test_missing_fields(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "mf", manifest={
            "name": "", "version": "", "type": "handler", "entry_point": "p.py",
        })
        result = runner._test_plugin_metadata("mf")
        assert result.passed is False
        assert "missing name" in result.message
        assert "missing version" in result.message

    def test_missing_description(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "md", manifest={
            "name": "md", "version": "1.0", "type": "handler",
            "entry_point": "p.py", "description": "",
        })
        result = runner._test_plugin_metadata("md")
        assert result.passed is False
        assert "missing description" in result.message

    def test_json_error(self, runner, tmp_path):
        d = tmp_path / "je"
        d.mkdir()
        (d / "plugin.json").write_text("{bad")
        result = runner._test_plugin_metadata("je")
        assert result.passed is False


# ===================================================================
# _test_plugin_type_methods  (lines 258-341)  — 7 branches
# ===================================================================

class TestPluginTypeMethods:
    def test_no_manifest(self, runner, tmp_path):
        (tmp_path / "ntm").mkdir()
        result = runner._test_plugin_type_methods("ntm")
        assert result.passed is False

    def test_unknown_type_passes(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "ut",
                         manifest={"name": "ut", "version": "1.0",
                                   "type": "unknown_xyz", "entry_point": "plugin.py"},
                         code="class Foo: pass")
        result = runner._test_plugin_type_methods("ut")
        assert result.passed is True  # unknown type has no required methods

    def test_handler_all_methods_present(self, runner, good_handler):
        result = runner._test_plugin_type_methods("good_handler")
        assert result.passed is True

    def test_handler_missing_methods(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "incomplete_h",
                         manifest={"name": "incomplete_h", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py",
                                   "entry_class": "IncompleteH"},
                         code="class IncompleteH:\n    def can_handle(self, u): return False")
        result = runner._test_plugin_type_methods("incomplete_h")
        assert result.passed is False
        assert "Missing methods" in result.message

    def test_auto_discover_for_methods(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "auto_m",
                         manifest={"name": "auto_m", "version": "1.0",
                                   "type": "validator", "entry_point": "plugin.py"},
                         code=VALIDATOR_CODE)
        result = runner._test_plugin_type_methods("auto_m")
        assert result.passed is True

    def test_no_instance_found(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "no_inst",
                         manifest={"name": "no_inst", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py"},
                         code="class NotHandler:\n    pass")
        result = runner._test_plugin_type_methods("no_inst")
        assert result.passed is False
        assert "Could not instantiate" in result.message

    def test_import_error(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "imp",
                         manifest={"name": "imp", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py"})
        (tmp_path / "imp" / "plugin.py").write_text("raise ImportError('x')")
        result = runner._test_plugin_type_methods("imp")
        assert result.passed is False


# ===================================================================
# _test_type_class_match  (lines 343-412)  — 6 branches
# ===================================================================

class TestTypeClassMatch:
    def test_no_manifest(self, runner, tmp_path):
        (tmp_path / "ntcm").mkdir()
        result = runner._test_type_class_match("ntcm")
        assert result.passed is False

    def test_no_entry_class_skipped(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "legacy",
                         manifest={"name": "legacy", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py"})
        result = runner._test_type_class_match("legacy")
        assert result.passed is True
        assert "skipped" in result.message

    def test_match_found(self, runner, good_handler):
        result = runner._test_type_class_match("good_handler")
        assert result.passed is True

    def test_mismatch(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "mismatch",
                         manifest={"name": "mismatch", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py",
                                   "entry_class": "TestExport"},
                         code=EXPORT_CODE)
        result = runner._test_type_class_match("mismatch")
        assert result.passed is False
        assert "not subclass" in result.message.lower()

    def test_class_not_found(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "cnf",
                         manifest={"name": "cnf", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py",
                                   "entry_class": "GhostClass"})
        (tmp_path / "cnf" / "plugin.py").write_text("class Foo: pass")
        result = runner._test_type_class_match("cnf")
        assert result.passed is False
        assert "not found" in result.message.lower()

    def test_unknown_type(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "unk",
                         manifest={"name": "unk", "version": "1.0",
                                   "type": "bogus", "entry_point": "plugin.py",
                                   "entry_class": "Foo"},
                         code="class Foo: pass")
        result = runner._test_type_class_match("unk")
        assert result.passed is False
        assert "Unknown type" in result.message


# ===================================================================
# test_all  (lines 414-422)  — 3 branches
# ===================================================================

class TestTestAll:
    def test_dir_missing(self, runner, tmp_path):
        nonexistent = tmp_path / "no_such_dir"
        runner.plugins_dir = nonexistent
        result = runner.test_all()
        assert result == []

    def test_valid_plugins(self, runner, tmp_path):
        _make_plugin_dir(tmp_path, "p1", code=HANDLER_CODE,
                         manifest={"name": "p1", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py",
                                   "description": "d", "entry_class": "TestHandler"})
        suites = runner.test_all()
        assert len(suites) == 1
        assert suites[0].plugin_name == "p1"

    def test_hidden_and_no_manifest_skipped(self, runner, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "plugin.json").write_text("{}")
        (tmp_path / "nomanifest").mkdir()
        _make_plugin_dir(tmp_path, "real", code=HANDLER_CODE,
                         manifest={"name": "real", "version": "1.0",
                                   "type": "handler", "entry_point": "plugin.py",
                                   "description": "d"})
        suites = runner.test_all()
        assert len(suites) == 1
        assert suites[0].plugin_name == "real"
