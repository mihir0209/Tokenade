"""Cross-platform process helpers (stdlib only, no new dependencies)."""

from __future__ import annotations


def windows_pid_alive(pid: int) -> bool:
    """True if a process with *pid* is currently running on Windows.

    Uses OpenProcess + GetExitCodeProcess via stdlib ctypes. Conservative on
    errors: anything except "no such PID" (ERROR_INVALID_PARAMETER) is
    treated as alive, so callers never act on a process they cannot query
    (e.g. refuse to steal its lock file).
    """
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:  # pragma: no cover - CPython always ships ctypes
        return True
    try:
        kernel32 = ctypes.windll.kernel32
    except AttributeError:  # non-Windows interpreter
        return True
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    ERROR_INVALID_PARAMETER = 87
    STILL_ACTIVE = 259
    try:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except Exception:
        return True
    if not handle:
        return kernel32.GetLastError() != ERROR_INVALID_PARAMETER
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)
