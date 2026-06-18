"""Comprehensive tests for fingerprint collectors - audio and fonts modules."""

from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# AudioCollector tests
# ---------------------------------------------------------------------------

class TestAudioCollector:
    def _make(self):
        from tokenade.core.fingerprint.collectors.audio import AudioCollector
        return AudioCollector()

    def test_api_name(self):
        c = self._make()
        assert c.api_name == "audio"

    def test_collect_success(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = {
            "sampleRate": 44100,
            "channelCount": 2,
            "channelCountMode": "explicit",
            "fftSize": 2048,
            "hash": "10,20,30",
        }
        result = c.collect(bm)
        assert result["sampleRate"] == 44100
        assert result["channelCount"] == 2
        assert result["channelCountMode"] == "explicit"
        assert result["fftSize"] == 2048
        assert result["hash"] == "10,20,30"
        bm.evaluate.assert_called_once()

    def test_collect_returns_empty_on_non_dict(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = "not a dict"
        result = c.collect(bm)
        assert result == {}

    def test_collect_returns_empty_on_none(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = None
        result = c.collect(bm)
        assert result == {}

    def test_collect_returns_empty_on_exception(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.side_effect = RuntimeError("browser crashed")
        result = c.collect(bm)
        assert result == {}

    def test_collect_returns_empty_on_empty_dict(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = {}
        result = c.collect(bm)
        assert result == {}

    def test_get_script_template(self):
        c = self._make()
        tpl = c.get_script_template()
        assert isinstance(tpl, str)
        assert "sampleRate" in tpl
        assert "channelCount" in tpl
        assert "channelCountMode" in tpl
        assert "fftSize" in tpl
        assert "audioHash" in tpl
        assert "origAudioContext" in tpl

    def test_build_script_from_template(self):
        c = self._make()
        data = {
            "sampleRate": 48000,
            "channelCount": 2,
            "channelCountMode": "max",
            "fftSize": 1024,
            "hash": "1,2,3,4",
        }
        script = c.build_script(data)
        assert "48000" in script
        assert "1024" in script
        assert "max" in script
        assert "1,2,3,4" in script

    def test_collect_calls_correct_script(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = {}
        c.collect(bm)
        called_script = bm.evaluate.call_args[0][0]
        assert "AudioContext" in called_script
        assert "createOscillator" in called_script
        assert "createAnalyser" in called_script

    def test_collect_with_complex_audio_data(self):
        c = self._make()
        bm = MagicMock()
        freq_data = ",".join(str(i % 256) for i in range(50))
        bm.evaluate.return_value = {
            "sampleRate": 96000,
            "channelCount": 6,
            "channelCountMode": "clamped-max",
            "fftSize": 4096,
            "hash": freq_data,
        }
        result = c.collect(bm)
        assert result["sampleRate"] == 96000
        assert result["channelCount"] == 6
        assert len(result["hash"].split(",")) == 50

    def test_build_script_bool_replacement(self):
        c = self._make()
        tpl = c.get_script_template()
        assert isinstance(tpl, str)


# ---------------------------------------------------------------------------
# FontsCollector tests
# ---------------------------------------------------------------------------

class TestFontsCollector:
    def _make(self):
        from tokenade.core.fingerprint.collectors.fonts import FontsCollector
        return FontsCollector()

    def test_api_name(self):
        c = self._make()
        assert c.api_name == "fonts"

    def test_collect_success(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = {
            "fonts": ["Arial", "Verdana"],
            "measurements": {
                "Arial": {"width": 100.0, "diff": 2.0},
                "Verdana": {"width": 102.0, "diff": 4.0},
            },
        }
        result = c.collect(bm)
        assert result["fonts"] == ["Arial", "Verdana"]
        assert "Arial" in result["measurements"]
        bm.evaluate.assert_called_once()

    def test_collect_returns_empty_on_non_dict(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = [1, 2, 3]
        result = c.collect(bm)
        assert result == {}

    def test_collect_returns_empty_on_none(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = None
        result = c.collect(bm)
        assert result == {}

    def test_collect_returns_empty_on_exception(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.side_effect = Exception("page crashed")
        result = c.collect(bm)
        assert result == {}

    def test_collect_returns_empty_on_string(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = "unexpected"
        result = c.collect(bm)
        assert result == {}

    def test_collect_returns_empty_on_empty_dict(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = {}
        result = c.collect(bm)
        assert result == {}

    def test_get_script_template(self):
        c = self._make()
        tpl = c.get_script_template()
        assert isinstance(tpl, str)
        assert "Fonts spoofing" in tpl

    def test_collect_script_references_canvas(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = {"fonts": [], "measurements": {}}
        c.collect(bm)
        called_script = bm.evaluate.call_args[0][0]
        assert "canvas" in called_script
        assert "measureText" in called_script
        assert "Arial" in called_script

    def test_collect_with_all_standard_fonts(self):
        c = self._make()
        bm = MagicMock()
        fonts = [
            "Arial", "Times New Roman", "Courier New", "Georgia", "Verdana",
            "Helvetica", "Tahoma", "Trebuchet MS", "Impact", "Comic Sans MS",
        ]
        measurements = {f: {"width": 100.0 + i, "diff": float(i)} for i, f in enumerate(fonts)}
        bm.evaluate.return_value = {"fonts": fonts, "measurements": measurements}
        result = c.collect(bm)
        assert len(result["fonts"]) == 10
        assert len(result["measurements"]) == 10

    def test_collect_measurement_values(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = {
            "fonts": ["Arial"],
            "measurements": {"Arial": {"width": 435.2, "diff": 0.0}},
        }
        result = c.collect(bm)
        m = result["measurements"]["Arial"]
        assert m["width"] == 435.2
        assert m["diff"] == 0.0

    def test_collect_handles_bool_return(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = True
        result = c.collect(bm)
        assert result == {}

    def test_collect_handles_int_return(self):
        c = self._make()
        bm = MagicMock()
        bm.evaluate.return_value = 42
        result = c.collect(bm)
        assert result == {}


# ---------------------------------------------------------------------------
# BaseCollector.build_script tests (via AudioCollector)
# ---------------------------------------------------------------------------

class TestBaseCollectorBuildScript:
    def test_build_script_bool_value(self):
        from tokenade.core.fingerprint.collectors.audio import AudioCollector
        AudioCollector()

        class FakeTpl:
            def get_script_template(self):
                return "var x = {{flag}};"
        # Use a minimal collector that has a bool placeholder
        from tokenade.core.fingerprint.collectors.base import BaseCollector

        class TestCollector(BaseCollector):
            @property
            def api_name(self):
                return "test"

            def collect(self, browser_manager):
                return {}

            def get_script_template(self):
                return "var flag = {{flag}};"

        tc = TestCollector()
        script = tc.build_script({"flag": True})
        assert "true" in script

    def test_build_script_float_value(self):
        from tokenade.core.fingerprint.collectors.base import BaseCollector

        class TC(BaseCollector):
            @property
            def api_name(self):
                return "t"

            def collect(self, bm):
                return {}

            def get_script_template(self):
                return "var r = {{ratio}};"

        tc = TC()
        script = tc.build_script({"ratio": 1.5})
        assert "1.5" in script

    def test_build_script_list_value(self):
        from tokenade.core.fingerprint.collectors.base import BaseCollector

        class TC(BaseCollector):
            @property
            def api_name(self):
                return "t"

            def collect(self, bm):
                return {}

            def get_script_template(self):
                return "var f = {{fonts}};"

        tc = TC()
        script = tc.build_script({"fonts": ["Arial", "Helvetica"]})
        assert "Arial" in script
        assert "Helvetica" in script

    def test_build_script_dict_value(self):
        from tokenade.core.fingerprint.collectors.base import BaseCollector

        class TC(BaseCollector):
            @property
            def api_name(self):
                return "t"

            def collect(self, bm):
                return {}

            def get_script_template(self):
                return "var m = {{data}};"

        tc = TC()
        script = tc.build_script({"data": {"key": "val"}})
        assert "key" in script

    def test_build_script_none_value(self):
        from tokenade.core.fingerprint.collectors.base import BaseCollector

        class TC(BaseCollector):
            @property
            def api_name(self):
                return "t"

            def collect(self, bm):
                return {}

            def get_script_template(self):
                return "var n = {{val}};"

        tc = TC()
        script = tc.build_script({"val": None})
        assert "None" in script

    def test_build_script_string_value(self):
        from tokenade.core.fingerprint.collectors.base import BaseCollector

        class TC(BaseCollector):
            @property
            def api_name(self):
                return "t"

            def collect(self, bm):
                return {}

            def get_script_template(self):
                return "var s = {{text}};"

        tc = TC()
        script = tc.build_script({"text": "hello world"})
        assert "hello world" in script

    def test_build_script_no_placeholders(self):
        from tokenade.core.fingerprint.collectors.base import BaseCollector

        class TC(BaseCollector):
            @property
            def api_name(self):
                return "t"

            def collect(self, bm):
                return {}

            def get_script_template(self):
                return "var x = 1;"

        tc = TC()
        script = tc.build_script({"ignored": "val"})
        assert script == "var x = 1;"

    def test_build_script_int_value(self):
        from tokenade.core.fingerprint.collectors.base import BaseCollector

        class TC(BaseCollector):
            @property
            def api_name(self):
                return "t"

            def collect(self, bm):
                return {}

            def get_script_template(self):
                return "var n = {{count}};"

        tc = TC()
        script = tc.build_script({"count": 42})
        assert "42" in script
