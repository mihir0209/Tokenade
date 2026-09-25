"""Pure-Python LevelDB reader for Chromium localStorage extraction.

Chromium stores localStorage in ``<profile>/Local Storage/leveldb/`` using
Google's LevelDB format. The historical reader needs ``plyvel`` (Linux-only
binary wheels), which leaves Windows/macOS with empty storage exports for
sites like Discord and Telegram.

This module reads the format directly with the standard library only:

- ``*.log`` — WriteBatch record logs (current writes, uncompressed)
- ``*.ldb`` — Sorted tables (Snappy or uncompressed data blocks)

Records are merged with LevelDB semantics: the highest sequence number wins,
deletions drop the key. Live files (browser running) are read tolerantly —
torn tail records and checksum mismatches are skipped, never fatal.

Chromium localStorage layout inside LevelDB:

- Key: ``_<origin>\\x00\\x01<js_key>`` (plus ``META:<origin>`` bookkeeping
  keys, which are ignored)
- Value: ``\\x01`` + UTF-8 text, ``\\x00`` + UTF-16-LE text, or OSCrypt
  ``v10``/``v11`` encrypted bytes
"""

import glob
import logging
import os
import struct
from typing import Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# LevelDB table magic number 0xdb4775248b80fb57, little-endian on disk.
# (Verified byte-for-byte against real Chromium *.ldb files.)
_SSTABLE_MAGIC = bytes([0x57, 0xFB, 0x80, 0x8B, 0x24, 0x75, 0x47, 0xDB])
_LOG_BLOCK = 32 * 1024
_LOG_HEADER = 7
_MASK_DELTA = 0xA282EAD8

# WriteBatch record types.
_RECORD_DELETION = 0
_RECORD_VALUE = 1


# ---------------------------------------------------------------------------
# CRC32C (Castagnoli) + LevelDB masking
# ---------------------------------------------------------------------------

def _crc32c_table():
    poly = 0x82F63B78  # reflected form of 0x1EDC6F41
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ poly if crc & 1 else crc >> 1
        table.append(crc & 0xFFFFFFFF)
    return table


_CRC32C_TABLE = _crc32c_table()


def crc32c(data: bytes, crc: int = 0xFFFFFFFF) -> int:
    """CRC32C checksum (all-ones init + final XOR), verified against real
    Chromium LevelDB record headers (``b"123456789"`` -> ``0xE3069283``)."""
    for byte in data:
        crc = _CRC32C_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF


def mask_crc(crc: int) -> int:
    """LevelDB checksum masking applied before storage."""
    return (((crc >> 15) | (crc << 17)) + _MASK_DELTA) & 0xFFFFFFFF


def unmask_crc(masked: int) -> int:
    """Invert :func:`mask_crc`."""
    rot = (masked - _MASK_DELTA) & 0xFFFFFFFF
    return (((rot << 15) | (rot >> 17)) & 0xFFFFFFFF)


# ---------------------------------------------------------------------------
# Varints
# ---------------------------------------------------------------------------

def decode_varint32(data: bytes, pos: int) -> Tuple[int, int]:
    """Return ``(value, new_pos)``; raises ValueError on truncation."""
    result = 0
    shift = 0
    while shift < 35:
        if pos >= len(data):
            raise ValueError("truncated varint32")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
    raise ValueError("varint32 overflow")


def encode_varint32(value: int) -> bytes:
    """Encode helper (tests / fixtures only)."""
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


# ---------------------------------------------------------------------------
# Snappy raw-block decompression (no framing/xpress wrapper)
# ---------------------------------------------------------------------------

def snappy_decompress(data: bytes) -> bytes:
    """Decompress a raw Snappy block. Raises ValueError on corrupt input."""
    length, pos = decode_varint32(data, 0)
    out = bytearray()
    append = out.append
    extend = out.extend
    n = len(data)
    while pos < n:
        tag = data[pos]
        pos += 1
        kind = tag & 0x03
        if kind == 0:
            size = tag >> 2
            if size < 60:
                size += 1
            else:
                extra = size - 59
                if pos + extra > n:
                    raise ValueError("truncated snappy literal length")
                size = 1
                for i in range(extra):
                    size += data[pos + i] << (8 * i)
                pos += extra
            if pos + size > n:
                raise ValueError("truncated snappy literal")
            extend(data[pos:pos + size])
            pos += size
        else:
            if kind == 1:
                if pos >= n:
                    raise ValueError("truncated snappy copy-1")
                size = ((tag >> 2) & 0x07) + 4
                offset = ((tag >> 5) << 8) | data[pos]
                pos += 1
            elif kind == 2:
                if pos + 2 > n:
                    raise ValueError("truncated snappy copy-2")
                size = (tag >> 2) + 1
                offset = data[pos] | (data[pos + 1] << 8)
                pos += 2
            else:
                if pos + 4 > n:
                    raise ValueError("truncated snappy copy-4")
                size = (tag >> 2) + 1
                offset = struct.unpack_from("<I", data, pos)[0]
                pos += 4
            if offset == 0 or offset > len(out):
                raise ValueError("invalid snappy copy offset")
            for _ in range(size):
                append(out[len(out) - offset])
    if len(out) != length:
        raise ValueError(
            "snappy length mismatch: header %d, got %d" % (length, len(out))
        )
    return bytes(out)


# ---------------------------------------------------------------------------
# Log (*.log) — WriteBatch records
# ---------------------------------------------------------------------------

def _read_log_batches(data: bytes) -> Iterator[Tuple[int, int, bytes, bytes]]:
    """Yield ``(seq, tag, key, value)`` from a *.log file image.

    Stops cleanly at torn tail records (live browser appending).
    """
    pos = 0
    n = len(data)
    pending: Dict[int, List[bytes]] = {}
    while pos + _LOG_HEADER <= n:
        block_off = pos % _LOG_BLOCK
        if block_off + _LOG_HEADER > _LOG_BLOCK:
            pos += _LOG_BLOCK - block_off  # trailer padding
            continue
        crc_stored, length, rtype = struct.unpack_from("<IHB", data, pos)
        if length == 0 and rtype == 0:
            break  # clean EOF padding
        if rtype not in (1, 2, 3, 4):
            break  # not a record header (garbage/tail)
        pos += _LOG_HEADER
        if pos + length > n:
            break  # torn tail (live append)
        payload = data[pos:pos + length]
        pos += length
        # Verify masked crc the LevelDB way: crc over (type byte + payload).
        masked = mask_crc(crc32c(bytes([rtype]) + payload))
        if masked != crc_stored:
            # Corrupt/torn fragment: drop pending assembly, resync at next
            # block boundary instead of aborting the whole file.
            pending.pop(rtype, None)
            while pos % _LOG_BLOCK != 0 and pos < n:
                pos += 1
            continue
        chunk_id = rtype
        if rtype == 1:  # FULL
            yield from _parse_batch(payload)
        else:
            buf = pending.setdefault(chunk_id, [])
            buf.append(payload)
            if rtype == 4:  # LAST
                assembled = b"".join(buf)
                del pending[chunk_id]
                yield from _parse_batch(assembled)


def _parse_batch(payload: bytes) -> Iterator[Tuple[int, int, bytes, bytes]]:
    """Yield ``(seq, tag, key, value)`` from one WriteBatch payload."""
    if len(payload) < 12:
        return
    seq = struct.unpack_from("<Q", payload, 0)[0]
    count = struct.unpack_from("<I", payload, 8)[0]
    pos = 12
    for _ in range(count):
        if pos >= len(payload):
            return
        tag = payload[pos]
        pos += 1
        try:
            key_len, pos = decode_varint32(payload, pos)
            key = payload[pos:pos + key_len]
            pos += key_len
            value = b""
            if tag == _RECORD_VALUE:
                value_len, pos = decode_varint32(payload, pos)
                value = payload[pos:pos + value_len]
                pos += value_len
        except (ValueError, IndexError):
            return
        yield seq, tag, bytes(key), bytes(value)


# ---------------------------------------------------------------------------
# Sorted tables (*.ldb) — block + restart-point format
# ---------------------------------------------------------------------------

def _read_block(data: bytes, offset: int, size: int) -> Optional[bytes]:
    """Read + decompress one SSTable data/index block (with trailer)."""
    end = offset + size
    if end + 5 > len(data):
        return None
    raw = data[offset:end]
    comp_type = data[end]
    stored_crc = struct.unpack_from("<I", data, end + 1)[0]
    if unmask_crc(stored_crc) != crc32c(raw + bytes([comp_type])):
        logger.debug("sstable block checksum mismatch at %d", offset)
        return None
    if comp_type == 0:
        return raw
    if comp_type == 1:
        try:
            return snappy_decompress(raw)
        except ValueError as e:
            logger.debug("snappy decode failed at %d: %s", offset, e)
            return None
    logger.debug("unknown sstable compression %d at %d", comp_type, offset)
    return None


def _iter_block_entries(block: bytes) -> Iterator[Tuple[bytes, bytes]]:
    """Yield ``(internal_key, value)`` from a decompressed data/index block."""
    if len(block) < 4:
        return
    num_restarts = struct.unpack_from("<I", block, len(block) - 4)[0]
    if 4 + num_restarts * 4 > len(block):
        return
    limit = len(block) - 4 - num_restarts * 4
    pos = 0
    last_key = b""
    while pos < limit:
        try:
            shared, pos = decode_varint32(block, pos)
            non_shared, pos = decode_varint32(block, pos)
            value_len, pos = decode_varint32(block, pos)
        except ValueError:
            return
        if pos + non_shared + value_len > limit:
            return
        key = last_key[:shared] + block[pos:pos + non_shared]
        pos += non_shared
        value = block[pos:pos + value_len]
        pos += value_len
        last_key = key
        yield bytes(key), bytes(value)


def _split_internal_key(internal: bytes) -> Optional[Tuple[bytes, int, int]]:
    """Split internal key into ``(user_key, sequence, kind)``."""
    if len(internal) < 8:
        return None
    trailer = struct.unpack_from("<Q", internal, len(internal) - 8)[0]
    return internal[:-8], trailer >> 8, trailer & 0xFF


def _read_table_handles(data: bytes) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """Return ``((meta_off, meta_len), (index_off, index_len))`` from footer.

    The footer is always 48 bytes: two BlockHandles, zero padding, then
    the 8-byte magic. Handles are self-consistency checked against the
    file size so a corrupt footer is rejected instead of misparsed.
    """
    if len(data) < 48 or data[-8:] != _SSTABLE_MAGIC:
        return None
    try:
        pos = len(data) - 48
        meta_off, pos = decode_varint32(data, pos)
        meta_len, pos = decode_varint32(data, pos)
        index_off, pos = decode_varint32(data, pos)
        index_len, _ = decode_varint32(data, pos)
    except ValueError:
        return None
    if index_off + index_len + 5 + 48 != len(data):
        return None
    return (meta_off, meta_len), (index_off, index_len)


def _read_sstable_records(data: bytes) -> Iterator[Tuple[int, int, bytes, bytes]]:
    """Yield ``(seq, tag, user_key, value)`` from an *.ldb file image."""
    handles = _read_table_handles(data)
    if handles is None:
        return
    _, (index_off, index_len) = handles
    index_block = _read_block(data, index_off, index_len)
    if index_block is None:
        return
    for _, handle_value in _iter_block_entries(index_block):
        try:
            pos = 0
            data_off, pos = decode_varint32(handle_value, pos)
            data_len, _ = decode_varint32(handle_value, pos)
        except ValueError:
            continue
        block = _read_block(data, data_off, data_len)
        if block is None:
            continue
        for internal_key, value in _iter_block_entries(block):
            split = _split_internal_key(internal_key)
            if split is None:
                continue
            user_key, seq, kind = split
            tag = _RECORD_VALUE if kind == 1 else _RECORD_DELETION
            yield seq, tag, user_key, value


# ---------------------------------------------------------------------------
# Merge + Chromium localStorage decoding
# ---------------------------------------------------------------------------

def iter_merged_records(leveldb_dir: str) -> Iterator[Tuple[bytes, bytes]]:
    """Yield ``(user_key, value)`` merged across *.log + *.ldb, newest wins.

    Newest = highest LevelDB sequence number; deletions drop the key.
    Corrupt files/records are skipped with a debug log, never fatal
    (browsers hold these files open while running).
    """
    best: Dict[bytes, Tuple[int, int, bytes]] = {}
    try:
        names = sorted(os.listdir(leveldb_dir))
    except OSError as e:
        logger.debug("cannot list leveldb dir %s: %s", leveldb_dir, e)
        return
    order = 0
    for name in names:
        path = os.path.join(leveldb_dir, name)
        records = None
        try:
            if name.endswith(".log"):
                with open(path, "rb") as f:
                    records = list(_read_log_batches(f.read()))
            elif name.endswith(".ldb"):
                with open(path, "rb") as f:
                    records = list(_read_sstable_records(f.read()))
            else:
                continue
        except OSError as e:
            logger.debug("cannot read leveldb file %s: %s", path, e)
            continue
        except Exception as e:
            logger.debug("failed parsing leveldb file %s: %s", path, e)
            continue
        order += 1
        for seq, tag, key, value in records:
            prev = best.get(key)
            if prev is None or (seq, order) >= (prev[0], prev[1]):
                best[key] = (seq, order, value if tag == _RECORD_VALUE else None)
    for key, (_, _, value) in best.items():
        if value is not None:
            yield key, value


def split_chromium_key(user_key: bytes) -> Optional[Tuple[str, str]]:
    """Split ``_<origin>\\x00\\x01<js_key>`` into ``(origin, js_key)``."""
    try:
        text = user_key.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not text.startswith("_"):
        return None
    parts = text[1:].split("\x00", 1)
    if len(parts) != 2:
        return None
    origin, js_key = parts
    if js_key.startswith("\x01"):
        js_key = js_key[1:]
    if not origin or not js_key:
        return None
    return origin, js_key


def decode_chromium_value(value: bytes, oscrypt_key: Optional[bytes] = None) -> Optional[str]:
    """Decode a Chromium localStorage value to text.

    ``\\x01`` + UTF-8 and ``\\x00`` + UTF-16-LE are Chromium's plaintext
    markers; ``v10``/``v11`` values are OSCrypt-encrypted (AES-GCM on
    Windows, AES-CBC on Linux/macOS) and need ``oscrypt_key``.
    """
    if not value:
        return ""
    if value[:1] == b"\x00":
        try:
            return value[1:].decode("utf-16-le")
        except UnicodeDecodeError:
            return None
    if value[:1] == b"\x01":
        try:
            return value[1:].decode("utf-8")
        except UnicodeDecodeError:
            return None
    if value[:3] in (b"v10", b"v11"):
        if oscrypt_key is None:
            return None
        try:
            return _decrypt_oscrypt_storage(value, oscrypt_key)
        except Exception as e:
            logger.debug("oscrypt storage decrypt failed: %s", e)
            return None
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _decrypt_oscrypt_storage(value: bytes, key: bytes) -> str:
    """Decrypt an OSCrypt localStorage value (unlike cookies: no metadata skip)."""
    import platform

    system = platform.system()
    if system == "Windows":
        try:
            from Crypto.Cipher import AES
        except ImportError:
            raise RuntimeError("pycryptodome required for OSCrypt values")
        nonce, ciphertext = value[3:15], value[15:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext[:-16], ciphertext[-16:]).decode("utf-8")
    # Linux/macOS Chromium: AES-128-CBC, IV of 16 spaces, PBKDF2 key.
    try:
        from Crypto.Cipher import AES
    except ImportError:
        raise RuntimeError("pycryptodome required for OSCrypt values")
    iv = b" " * 16
    cipher = AES.new(key[:16], AES.MODE_CBC, iv)
    padded = cipher.decrypt(value[3:])
    pad_len = padded[-1] if padded else 0
    if 1 <= pad_len <= 16:
        padded = padded[:-pad_len]
    return padded.decode("utf-8")


def extract_origin(
    leveldb_dir: str,
    origin: str,
    oscrypt_key: Optional[bytes] = None,
) -> Dict[str, str]:
    """Return ``{js_key: text}`` localStorage for one origin."""
    result = {}
    for user_key, value in iter_merged_records(leveldb_dir):
        split = split_chromium_key(user_key)
        if split is None:
            continue
        rec_origin, js_key = split
        if rec_origin != origin:
            continue
        text = decode_chromium_value(value, oscrypt_key)
        if text is not None:
            result[js_key] = text
    return result


def list_origins(leveldb_dir: str) -> List[str]:
    """Return sorted origins present in the LevelDB."""
    origins = set()
    for user_key, _ in iter_merged_records(leveldb_dir):
        split = split_chromium_key(user_key)
        if split is not None:
            origins.add(split[0])
    return sorted(origins)
