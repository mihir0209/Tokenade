from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock

from tokenade.plugin import PluginResult, SiteHandlerPlugin


class ProfileDataHandler(SiteHandlerPlugin):
    name = "profile-data-handler"

    def extract_session(self, browser_context, url):
        return PluginResult(success=True)

    def inject_session(self, browser_context, session):
        return PluginResult(success=True)


def test_profile_data_hooks_default_to_noop(tmp_path):
    handler = ProfileDataHandler()

    exported = handler.export_profile_data(str(tmp_path), "brave")
    restored = handler.restore_profile_data({}, str(tmp_path), "brave")

    assert exported.success and exported.data == {}
    assert restored.success and restored.data == {}
