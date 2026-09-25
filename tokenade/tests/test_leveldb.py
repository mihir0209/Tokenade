"""Tests for the pure-Python LevelDB reader (no plyvel dependency)."""
import os
import struct
import unittest

from tokenade.core.importer import leveldb
from tokenade.core.importer.leveldb import (
    crc32c,
    decode_chromium_value,
    decode_varint32,
    encode_varint32,
    extract_origin,
    iter_merged_records,
    list_origins,
    mask_crc,
    snappy_decompress,
    split_chromium_key,
    unmask_crc,
)


def _frame_log_record(rtype, payload):
    masked = mask_crc(crc32c(bytes([rtype]) + payload))
    return struct.pack("<IHB", masked, len(payload), rtype) + payload


def _batch(seq, records):
    """records: list of (tag, key_bytes, value_bytes)."""
    out = bytearray(struct.pack("<QI", seq, len(records)))
    for tag, key, value in records:
        out.append(tag)
        out += encode_varint32(len(key)) + key
        if tag == 1:
            out += encode_varint32(len(value)) + value
    return bytes(out)


def _write_log(path, batches):
    with open(path, "wb") as f:
        for seq, records in batches:
            f.write(_frame_log_record(1, _batch(seq, records)))


def _block(entries):
    """Build an uncompressed block image from [(internal_key, value)]."""
    out = bytearray()
    restarts = []
    last = b""
    for key, value in entries:
        shared = 0
        while shared < min(len(last), len(key)) and last[shared] == key[shared]:
            shared += 1
        restarts.append(len(out))
        out += encode_varint32(shared)
        out += encode_varint32(len(key) - shared)
        out += encode_varint32(len(value))
        out += key[shared:]
        out += value
        last = key
    for r in restarts:
        out += struct.pack("<I", r)
    out += struct.pack("<I", len(restarts))
    return bytes(out)


def _block_with_trailer(block_data, comp=0):
    masked = mask_crc(crc32c(block_data + bytes([comp])))
    return block_data + bytes([comp]) + struct.pack("<I", masked)


def _internal(user_key, seq, kind=1):
    return user_key + struct.pack("<Q", (seq << 8) | kind)


def _write_sstable(path, internal_entries, comp=0):
    data_block = _block(internal_entries)
    if comp == 1:
        raise AssertionError("use _write_sstable_snappy for compressed tables")
    # Index value: BlockHandle(offset, size); size EXCLUDES the 5B trailer.
    index_block = _block([(internal_entries[-1][0],
                           encode_varint32(0) + encode_varint32(len(data_block)))])
    blob = bytearray()
    blob += _block_with_trailer(data_block, 0)
    index_off = len(blob)
    index_blob = _block_with_trailer(index_block, 0)
    blob += index_blob
    footer = bytearray()
    footer += encode_varint32(0) + encode_varint32(0)  # metaindex handle (empty)
    footer += encode_varint32(index_off) + encode_varint32(len(index_block))
    footer += b"\x00" * (48 - len(footer) - 8)
    footer += leveldb._SSTABLE_MAGIC
    assert len(footer) == 48
    blob += footer
    with open(path, "wb") as f:
        f.write(bytes(blob))


class TestCrc32c(unittest.TestCase):
    def test_vector(self):
        self.assertEqual(crc32c(b"123456789"), 0xE3069283)

    def test_mask_roundtrip(self):
        for v in (0, 1, 0xDEADBEEF, 0xFFFFFFFF):
            self.assertEqual(unmask_crc(mask_crc(v)), v)


class TestVarint(unittest.TestCase):
    def test_roundtrip(self):
        for v in (0, 1, 127, 128, 300, 2 ** 32 - 1):
            self.assertEqual(decode_varint32(encode_varint32(v), 0), (v, len(encode_varint32(v))))

    def test_truncated(self):
        with self.assertRaises(ValueError):
            decode_varint32(b"\x80", 0)


class TestSnappy(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(snappy_decompress(b"\x00"), b"")

    def test_literal(self):
        self.assertEqual(snappy_decompress(b"\x05\x10hello"), b"hello")

    def test_copy(self):
        # "hello hello": literal "hello " + copy-1byte (len 5, offset 6)
        blob = b"\x0b\x14hello \x05\x06"
        self.assertEqual(snappy_decompress(blob), b"hello hello")

    def test_corrupt(self):
        with self.assertRaises(ValueError):
            snappy_decompress(b"\x05\x10hi")  # length says 5, has 2


class TestLogBatches(unittest.TestCase):
    def test_newest_wins_and_delete_drops(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "000003.log")
            _write_log(p, [
                (10, [(1, b"k1", b"v1"), (1, b"k2", b"old")]),
                (11, [(0, b"k2", b""), (1, b"k1", b"v2")]),
            ])
            merged = dict(iter_merged_records(d))
            self.assertEqual(merged, {b"k1": b"v2"})
            self.assertNotIn(b"k2", merged)

    def test_torn_tail_tolerated(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "000003.log")
            _write_log(p, [(7, [(1, b"a", b"1")])])
            with open(p, "ab") as f:
                f.write(b"\x00\x00partial-garbage")
            merged = dict(iter_merged_records(d))
            self.assertEqual(merged, {b"a": b"1"})

    def test_missing_dir(self):
        self.assertEqual(list(iter_merged_records("/nonexistent-xyz")), [])


class TestSstable(unittest.TestCase):
    def _table(self, tmpdir, name="000010.ldb"):
        origin = b"_https://example.com\x00\x01"
        entries = [
            (_internal(origin + b"alpha", 5), b"\x01AAA"),
            (_internal(origin + b"beta", 6), b"\x01BBB"),
            (_internal(b"META:https://example.com", 6), b"junk"),
        ]
        p = os.path.join(tmpdir, name)
        _write_sstable(p, entries)
        return p

    def test_read_records(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._table(d)
            merged = dict(iter_merged_records(d))
            self.assertEqual(merged[b"_https://example.com\x00\x01alpha"], b"\x01AAA")
            self.assertEqual(merged[b"_https://example.com\x00\x01beta"], b"\x01BBB")

    def test_newest_wins_across_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            origin = b"_https://example.com\x00\x01"
            self._table(d, "000009.ldb")
            _write_sstable(os.path.join(d, "000011.ldb"),
                           [(_internal(origin + b"alpha", 9), b"\x01NEW")])
            merged = dict(iter_merged_records(d))
            self.assertEqual(merged[origin + b"alpha"], b"\x01NEW")

    def test_bad_magic_ignored(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "000010.ldb")
            with open(p, "wb") as f:
                f.write(b"not a table" * 10)
            self.assertEqual(list(iter_merged_records(d)), [])


class TestChromiumDecoding(unittest.TestCase):
    def test_split_key(self):
        self.assertEqual(
            split_chromium_key(b"_https://example.com\x00\x01mykey"),
            ("https://example.com", "mykey"),
        )
        self.assertIsNone(split_chromium_key(b"META:https://example.com"))
        self.assertIsNone(split_chromium_key(b"nope"))

    def test_markers(self):
        self.assertEqual(decode_chromium_value(b"\x01hello"), "hello")
        self.assertEqual(decode_chromium_value(b"\x00h\x00i\x00"), "hi")
        self.assertEqual(decode_chromium_value(b"plain"), "plain")
        self.assertEqual(decode_chromium_value(b""), "")

    def test_v10_windows(self):
        from Crypto.Cipher import AES
        key = b"k" * 32
        nonce = b"n" * 12
        ct = AES.new(key, AES.MODE_GCM, nonce=nonce).encrypt(b"secret!")
        import struct as _s
        blob = b"v10" + nonce + ct + b"\x00" * 16  # tag placeholder
        # recompute with real tag
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ct, tag = cipher.encrypt_and_digest(b"secret!")
        blob = b"v10" + nonce + ct + tag
        self.assertEqual(
            decode_chromium_value(blob, oscrypt_key=key), "secret!"
        )

    def test_v10_without_key(self):
        self.assertIsNone(decode_chromium_value(b"v10" + b"x" * 40))


class TestExtractOrigin(unittest.TestCase):
    def test_end_to_end(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            origin = b"_https://example.com\x00\x01"
            _write_log(os.path.join(d, "000003.log"), [
                (3, [(1, origin + b"k1", b"\x01v1"),
                     (1, origin + b"k2", b"\x01v2")]),
            ])
            _write_sstable(os.path.join(d, "000010.ldb"), [
                (_internal(b"_https://other.com\x00\x01z", 2), b"\x01Z"),
            ])
            self.assertEqual(
                extract_origin(d, "https://example.com"),
                {"k1": "v1", "k2": "v2"},
            )
            self.assertEqual(
                sorted(list_origins(d)),
                ["https://example.com", "https://other.com"],
            )


if __name__ == "__main__":
    unittest.main()
