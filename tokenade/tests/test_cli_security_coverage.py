"""Tests targeting uncovered lines in cli/security.py.

Uncovered lines:
  27-32     - interactive password prompt with confirmation in cmd_encrypt
  66-67     - load_key_from_file for decrypt
  71-72     - interactive password prompt in cmd_decrypt
  76        - fallback output path for decrypt
  89        - file size comparison in decrypt
  111-112   - load_key_from_file for old key in cmd_rekey
  116-117   - interactive old password prompt in cmd_rekey
  120-121   - load_key_from_file for new key in cmd_rekey
  125-130   - interactive new password prompt with confirmation in cmd_rekey
"""

from unittest.mock import patch, MagicMock
from argparse import Namespace

from tokenade.core.crypto.encryptor import TokenadeEncryptor
from tokenade.cli.security import cmd_encrypt, cmd_decrypt, cmd_rekey


def _encrypt_file(tmp_path, password="testpw"):
    enc = TokenadeEncryptor()
    src = tmp_path / "session.json"
    src.write_text('{"cookies": []}')
    enc_path = tmp_path / "session.json.encrypted"
    enc.encrypt_file(str(src), str(enc_path), password)
    return enc_path


# ---------------------------------------------------------------------------
# cmd_encrypt
# ---------------------------------------------------------------------------

class TestCmdEncrypt:
    def test_file_not_found(self, capsys):
        args = Namespace(input="/nonexistent/file", key_file=None, password=None, output=None)
        cmd_encrypt(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_password_arg(self, tmp_path, capsys):
        src = tmp_path / "plain.json"
        src.write_text('{"cookies":[]}')
        args = Namespace(input=str(src), key_file=None, password="mypass", output=None)
        cmd_encrypt(args)
        assert "encrypted" in capsys.readouterr().out.lower()

    def test_key_file_arg(self, tmp_path, capsys):
        src = tmp_path / "plain.json"
        src.write_text('{"cookies":[]}')
        keyfile = tmp_path / "key.txt"
        keyfile.write_text("filepw\n")
        args = Namespace(input=str(src), key_file=str(keyfile), password=None, output=None)
        cmd_encrypt(args)
        assert "encrypted" in capsys.readouterr().out.lower()

    @patch("getpass.getpass")
    def test_interactive_password_match(self, mock_getpass, tmp_path, capsys):
        """Lines 27-32: interactive password prompt with matching confirmation."""
        src = tmp_path / "plain.json"
        src.write_text('{"cookies":[]}')
        mock_getpass.side_effect = ["secret123", "secret123"]
        args = Namespace(input=str(src), key_file=None, password=None, output=None)
        cmd_encrypt(args)
        assert "encrypted" in capsys.readouterr().out.lower()

    @patch("getpass.getpass")
    def test_interactive_password_mismatch(self, mock_getpass, tmp_path, capsys):
        """Lines 30-32: passwords don't match."""
        src = tmp_path / "plain.json"
        src.write_text('{"cookies":[]}')
        mock_getpass.side_effect = ["pass1", "pass2"]
        args = Namespace(input=str(src), key_file=None, password=None, output=None)
        cmd_encrypt(args)
        assert "don't match" in capsys.readouterr().out

    def test_explicit_output(self, tmp_path, capsys):
        src = tmp_path / "plain.json"
        src.write_text('{"cookies":[]}')
        out = tmp_path / "custom.enc"
        args = Namespace(input=str(src), key_file=None, password="pw", output=str(out))
        cmd_encrypt(args)
        assert out.exists()

    def test_encryption_exception(self, tmp_path, capsys):
        src = tmp_path / "plain.json"
        src.write_text('{"cookies":[]}')
        args = Namespace(input=str(src), key_file=None, password="pw", output=None)
        with patch("tokenade.cli.security.encrypt_session", side_effect=RuntimeError("fail")):
            cmd_encrypt(args)
        assert "failed" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# cmd_decrypt
# ---------------------------------------------------------------------------

class TestCmdDecrypt:
    def test_file_not_found(self, capsys):
        args = Namespace(input="/nonexistent/file", key_file=None, password=None, output=None)
        cmd_decrypt(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_password_arg(self, tmp_path, capsys):
        enc_path = _encrypt_file(tmp_path)
        args = Namespace(input=str(enc_path), key_file=None, password="testpw", output=None)
        cmd_decrypt(args)
        assert "decrypted" in capsys.readouterr().out.lower()

    def test_key_file_arg(self, tmp_path, capsys):
        enc_path = _encrypt_file(tmp_path, "filepw")
        keyfile = tmp_path / "key.txt"
        keyfile.write_text("filepw\n")
        args = Namespace(input=str(enc_path), key_file=str(keyfile), password=None, output=None)
        cmd_decrypt(args)
        assert "decrypted" in capsys.readouterr().out.lower()

    @patch("getpass.getpass")
    def test_interactive_password(self, mock_getpass, tmp_path, capsys):
        """Lines 71-72: interactive password prompt for decrypt."""
        enc_path = _encrypt_file(tmp_path, "secret")
        mock_getpass.return_value = "secret"
        args = Namespace(input=str(enc_path), key_file=None, password=None, output=None)
        cmd_decrypt(args)
        assert "decrypted" in capsys.readouterr().out.lower()

    def test_fallback_output_no_encrypted_extension(self, tmp_path, capsys):
        """Line 76: file doesn't end in .encrypted -> output gets .decrypted suffix."""
        enc = TokenadeEncryptor()
        src = tmp_path / "data.txt"
        src.write_bytes(b"hello")
        enc_path = tmp_path / "data.txt"
        enc_path.write_bytes(enc.encrypt(b"hello", "pw"))
        args = Namespace(input=str(enc_path), key_file=None, password="pw", output=None)
        cmd_decrypt(args)
        output = tmp_path / "data.txt.decrypted"
        assert output.exists()

    def test_explicit_output(self, tmp_path, capsys):
        enc_path = _encrypt_file(tmp_path)
        out = tmp_path / "custom.dec"
        args = Namespace(input=str(enc_path), key_file=None, password="testpw", output=str(out))
        cmd_decrypt(args)
        assert out.exists()

    def test_wrong_password(self, tmp_path, capsys):
        enc_path = _encrypt_file(tmp_path, "right")
        args = Namespace(input=str(enc_path), key_file=None, password="wrong", output=None)
        cmd_decrypt(args)
        output = capsys.readouterr().out
        assert "wrong" in output.lower() or "failed" in output.lower()

    def test_decryption_exception(self, tmp_path, capsys):
        enc_path = _encrypt_file(tmp_path)
        args = Namespace(input=str(enc_path), key_file=None, password="testpw", output=None)
        with patch("tokenade.cli.security.decrypt_session", side_effect=Exception("generic")):
            cmd_decrypt(args)
        assert "failed" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# cmd_rekey
# ---------------------------------------------------------------------------

class TestCmdRekey:
    def test_file_not_found(self, capsys):
        args = Namespace(
            input="/nonexistent/file",
            old_key_file=None, old_password=None,
            new_key_file=None, new_password=None,
            output=None,
        )
        cmd_rekey(args)
        assert "not found" in capsys.readouterr().out.lower()

    def test_old_and_new_password_args(self, tmp_path, capsys):
        enc_path = _encrypt_file(tmp_path, "old")
        out = tmp_path / "rekeyed.bin"
        args = Namespace(
            input=str(enc_path),
            old_key_file=None, old_password="old",
            new_key_file=None, new_password="new",
            output=str(out),
        )
        cmd_rekey(args)
        assert "rekeyed" in capsys.readouterr().out.lower()

    def test_old_key_file(self, tmp_path, capsys):
        """Lines 111-112: load old key from file."""
        enc_path = _encrypt_file(tmp_path, "oldfilepw")
        keyfile = tmp_path / "oldkey.txt"
        keyfile.write_text("oldfilepw\n")
        args = Namespace(
            input=str(enc_path),
            old_key_file=str(keyfile), old_password=None,
            new_key_file=None, new_password="new",
            output=None,
        )
        cmd_rekey(args)
        assert "rekeyed" in capsys.readouterr().out.lower()

    def test_new_key_file(self, tmp_path, capsys):
        """Lines 120-121: load new key from file."""
        enc_path = _encrypt_file(tmp_path, "oldpw")
        keyfile = tmp_path / "newkey.txt"
        keyfile.write_text("newfilepw\n")
        args = Namespace(
            input=str(enc_path),
            old_key_file=None, old_password="oldpw",
            new_key_file=str(keyfile), new_password=None,
            output=None,
        )
        cmd_rekey(args)
        assert "rekeyed" in capsys.readouterr().out.lower()

    @patch("getpass.getpass")
    def test_interactive_old_password(self, mock_getpass, tmp_path, capsys):
        """Lines 116-117: interactive old password prompt."""
        enc_path = _encrypt_file(tmp_path, "old")
        mock_getpass.return_value = "old"
        args = Namespace(
            input=str(enc_path),
            old_key_file=None, old_password=None,
            new_key_file=None, new_password="new",
            output=None,
        )
        cmd_rekey(args)
        assert "rekeyed" in capsys.readouterr().out.lower()

    @patch("getpass.getpass")
    def test_interactive_new_password_match(self, mock_getpass, tmp_path, capsys):
        """Lines 125-130: interactive new password prompt with matching confirmation."""
        enc_path = _encrypt_file(tmp_path, "old")
        mock_getpass.side_effect = ["new", "new"]
        args = Namespace(
            input=str(enc_path),
            old_key_file=None, old_password="old",
            new_key_file=None, new_password=None,
            output=None,
        )
        cmd_rekey(args)
        assert "rekeyed" in capsys.readouterr().out.lower()

    @patch("getpass.getpass")
    def test_interactive_new_password_mismatch(self, mock_getpass, tmp_path, capsys):
        """Lines 128-130: new passwords don't match."""
        enc_path = _encrypt_file(tmp_path, "old")
        mock_getpass.side_effect = ["new", "different"]
        args = Namespace(
            input=str(enc_path),
            old_key_file=None, old_password="old",
            new_key_file=None, new_password=None,
            output=None,
        )
        cmd_rekey(args)
        assert "don't match" in capsys.readouterr().out

    def test_wrong_old_password(self, tmp_path, capsys):
        enc_path = _encrypt_file(tmp_path, "realold")
        args = Namespace(
            input=str(enc_path),
            old_key_file=None, old_password="wrong",
            new_key_file=None, new_password="new",
            output=None,
        )
        cmd_rekey(args)
        output = capsys.readouterr().out
        assert "wrong" in output.lower() or "failed" in output.lower()

    def test_rekey_exception(self, tmp_path, capsys):
        enc_path = _encrypt_file(tmp_path, "old")
        args = Namespace(
            input=str(enc_path),
            old_key_file=None, old_password="old",
            new_key_file=None, new_password="new",
            output=None,
        )
        with patch("tokenade.cli.security.TokenadeEncryptor") as mock_cls:
            mock_enc = MagicMock()
            mock_enc.rekey.side_effect = Exception("boom")
            mock_cls.return_value = mock_enc
            cmd_rekey(args)
        assert "failed" in capsys.readouterr().out.lower()
