"""
Cryptographic Memory Zeroization and SecureBuffer utilities.

Provides secure memory wiping (`ctypes.memset`) to prevent secrets,
encryption keys, and decrypted credentials from lingering in process memory.
"""

import ctypes
import os
from typing import Optional, Union


def zero_memory(target: Union[bytearray, memoryview, ctypes.Array, bytes]) -> None:
    """
    Overwrites the memory buffer with zeros in place.
    Safe for mutable buffers (bytearray, ctypes arrays, memoryviews).
    """
    if target is None:
        return

    if isinstance(target, bytearray):
        length = len(target)
        if length > 0:
            location = (ctypes.c_char * length).from_buffer(target)
            ctypes.memset(ctypes.addressof(location), 0, length)
    elif isinstance(target, memoryview):
        length = target.nbytes
        if length > 0 and not target.readonly:
            location = (ctypes.c_char * length).from_buffer(target)
            ctypes.memset(ctypes.addressof(location), 0, length)
    elif isinstance(target, (ctypes.Array, ctypes.Structure)):
        length = ctypes.sizeof(target)
        if length > 0:
            ctypes.memset(ctypes.addressof(target), 0, length)


class SecureBuffer:
    """
    RAII Context Manager wrapper for sensitive byte arrays.
    Guarantees in-place zeroization upon context exit or explicit close.
    """

    def __init__(self, data: Union[bytes, bytearray, str]):
        if isinstance(data, str):
            raw = data.encode("utf-8")
        else:
            raw = bytes(data)

        self._buf = bytearray(raw)
        self._length = len(self._buf)
        self._is_cleared = False

    @property
    def buffer(self) -> bytearray:
        if self._is_cleared:
            raise ValueError("SecureBuffer has already been zeroized")
        return self._buf

    @property
    def raw_bytes(self) -> bytes:
        if self._is_cleared:
            raise ValueError("SecureBuffer has already been zeroized")
        return bytes(self._buf)

    def wipe(self) -> None:
        """Securely wipe the internal buffer."""
        if not self._is_cleared and self._buf:
            zero_memory(self._buf)
            self._is_cleared = True

    def __enter__(self) -> "SecureBuffer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.wipe()

    def __del__(self):
        try:
            self.wipe()
        except Exception:
            pass
