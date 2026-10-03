"""Cloak path carries WebRTC lockdown flags to the binary command line."""
from unittest.mock import MagicMock, patch

from tokenade.core.browser.stealth.cloak import CloakBrowserBackend
from tokenade.core.session_runtime.webrtc import WEBRTC_LOCKDOWN_ARGS


def _ready_proc():
    proc = MagicMock()
    proc.poll.return_value = None
    return proc


def test_serve_cdp_forwards_extra_args(tmp_path):
    backend = CloakBrowserBackend()
    proc = _ready_proc()
    resp = MagicMock()
    resp.status = 200
    resp.__enter__.return_value = resp
    with patch.object(CloakBrowserBackend, "ensure_ready", return_value=True), \
         patch("tokenade.core.browser.stealth.cloak.get_binary_info",
               return_value={"binary_path": "C:\\cloak.exe"}), \
         patch("os.path.isfile", return_value=True), \
         patch("subprocess.Popen", return_value=proc) as popen, \
         patch("urllib.request.urlopen", return_value=resp):
        got = backend.serve_cdp(port=19222, headless=True,
                                user_data_dir=str(tmp_path),
                                extra_args=list(WEBRTC_LOCKDOWN_ARGS))
    assert got is proc
    cmd = " ".join(popen.call_args[0][0])
    assert WEBRTC_LOCKDOWN_ARGS[0] in cmd
    assert "--remote-debugging-port=19222" in cmd


def test_serve_cdp_without_extra_args_still_launches(tmp_path):
    backend = CloakBrowserBackend()
    proc = _ready_proc()
    resp = MagicMock()
    resp.status = 200
    resp.__enter__.return_value = resp
    with patch.object(CloakBrowserBackend, "ensure_ready", return_value=True), \
         patch("tokenade.core.browser.stealth.cloak.get_binary_info",
               return_value={"binary_path": "C:\\cloak.exe"}), \
         patch("os.path.isfile", return_value=True), \
         patch("subprocess.Popen", return_value=proc) as popen, \
         patch("urllib.request.urlopen", return_value=resp):
        backend.serve_cdp(port=19223, headless=True, user_data_dir=str(tmp_path))
    cmd = " ".join(popen.call_args[0][0])
    assert "webrtc" not in cmd.lower()
