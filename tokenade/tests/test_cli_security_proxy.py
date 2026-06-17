"""Tests for CLI security and proxy commands."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from argparse import Namespace

from tokenade.cli.security import cmd_encrypt, cmd_decrypt, cmd_rekey
from tokenade.cli.proxy import cmd_proxy


class TestCmdEncrypt:
    def test_input_not_found(self, capsys):
        args = Namespace(input="/nonexistent/session.tokenade", output=None, key_file=None, password="test")
        cmd_encrypt(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.encrypt_session")
    def test_encrypt_success(self, mock_encrypt, tmp_path, capsys):
        f = tmp_path / "session.tokenade"
        f.write_text('{"cookies": []}')
        mock_encrypt.return_value = str(tmp_path / "session.tokenade.encrypted")
        (tmp_path / "session.tokenade.encrypted").write_bytes(b"encrypted")

        args = Namespace(input=str(f), output=None, key_file=None, password="test")
        cmd_encrypt(args)
        assert "success" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.encrypt_session")
    def test_encrypt_with_output(self, mock_encrypt, tmp_path, capsys):
        f = tmp_path / "session.tokenade"
        f.write_text('{"cookies": []}')
        out = tmp_path / "custom_output.enc"
        mock_encrypt.return_value = str(out)
        out.write_bytes(b"encrypted")

        args = Namespace(input=str(f), output=str(out), key_file=None, password="test")
        cmd_encrypt(args)
        assert "success" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.encrypt_session")
    def test_encrypt_failure(self, mock_encrypt, tmp_path, capsys):
        f = tmp_path / "session.tokenade"
        f.write_text('{"cookies": []}')
        mock_encrypt.side_effect = Exception("Encryption error")

        args = Namespace(input=str(f), output=None, key_file=None, password="test")
        cmd_encrypt(args)
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.load_key_from_file")
    @patch("tokenade.cli.security.encrypt_session")
    def test_encrypt_with_key_file(self, mock_encrypt, mock_key, tmp_path, capsys):
        f = tmp_path / "session.tokenade"
        f.write_text('{"cookies": []}')
        key_f = tmp_path / "key.txt"
        key_f.write_text("secret")
        mock_key.return_value = "secret"
        mock_encrypt.return_value = str(tmp_path / "out.enc")
        (tmp_path / "out.enc").write_bytes(b"enc")

        args = Namespace(input=str(f), output=None, key_file=str(key_f), password=None)
        cmd_encrypt(args)
        assert "success" in capsys.readouterr().out.lower()


class TestCmdDecrypt:
    def test_input_not_found(self, capsys):
        args = Namespace(input="/nonexistent/encrypted.tokenade", output=None, key_file=None, password="test")
        cmd_decrypt(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.decrypt_session")
    def test_decrypt_success(self, mock_decrypt, tmp_path, capsys):
        f = tmp_path / "session.tokenade.encrypted"
        f.write_bytes(b"encrypted data")
        mock_decrypt.return_value = str(tmp_path / "session.tokenade")

        args = Namespace(input=str(f), output=None, key_file=None, password="test")
        cmd_decrypt(args)
        assert "success" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.decrypt_session")
    def test_decrypt_wrong_password(self, mock_decrypt, tmp_path, capsys):
        f = tmp_path / "session.tokenade.encrypted"
        f.write_bytes(b"encrypted data")
        mock_decrypt.side_effect = ValueError("Wrong password")

        args = Namespace(input=str(f), output=None, key_file=None, password="wrong")
        cmd_decrypt(args)
        assert "wrong password" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.decrypt_session")
    def test_decrypt_failure(self, mock_decrypt, tmp_path, capsys):
        f = tmp_path / "session.tokenade.encrypted"
        f.write_bytes(b"encrypted data")
        mock_decrypt.side_effect = Exception("Corrupted")

        args = Namespace(input=str(f), output=None, key_file=None, password="test")
        cmd_decrypt(args)
        assert "failed" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.decrypt_session")
    def test_decrypt_with_output(self, mock_decrypt, tmp_path, capsys):
        f = tmp_path / "session.encrypted"
        f.write_bytes(b"data")
        out = tmp_path / "decrypted.tokenade"
        mock_decrypt.return_value = str(out)

        args = Namespace(input=str(f), output=str(out), key_file=None, password="test")
        cmd_decrypt(args)
        assert "success" in capsys.readouterr().out.lower()


class TestCmdRekey:
    def test_input_not_found(self, capsys):
        args = Namespace(input="/nonexistent/file", output=None,
                         old_key_file=None, old_password="old",
                         new_key_file=None, new_password="new")
        cmd_rekey(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.TokenadeEncryptor")
    def test_rekey_success(self, mock_enc_cls, tmp_path, capsys):
        f = tmp_path / "session.encrypted"
        f.write_bytes(b"encrypted data")
        out = tmp_path / "rekeyed.encrypted"
        mock_enc = MagicMock()
        mock_enc.rekey.return_value = b"rekeyed data"
        mock_enc_cls.return_value = mock_enc

        args = Namespace(input=str(f), output=str(out),
                         old_key_file=None, old_password="old",
                         new_key_file=None, new_password="new")
        cmd_rekey(args)
        assert "success" in capsys.readouterr().out.lower()
        assert out.exists()

    @patch("tokenade.cli.security.TokenadeEncryptor")
    def test_rekey_wrong_password(self, mock_enc_cls, tmp_path, capsys):
        f = tmp_path / "session.encrypted"
        f.write_bytes(b"encrypted data")
        mock_enc = MagicMock()
        mock_enc.rekey.side_effect = ValueError("Wrong password")
        mock_enc_cls.return_value = mock_enc

        args = Namespace(input=str(f), output=None,
                         old_key_file=None, old_password="wrong",
                         new_key_file=None, new_password="new")
        cmd_rekey(args)
        assert "wrong" in capsys.readouterr().out.lower()

    @patch("tokenade.cli.security.TokenadeEncryptor")
    def test_rekey_failure(self, mock_enc_cls, tmp_path, capsys):
        f = tmp_path / "session.encrypted"
        f.write_bytes(b"encrypted data")
        mock_enc = MagicMock()
        mock_enc.rekey.side_effect = Exception("IO error")
        mock_enc_cls.return_value = mock_enc

        args = Namespace(input=str(f), output=None,
                         old_key_file=None, old_password="old",
                         new_key_file=None, new_password="new")
        cmd_rekey(args)
        assert "failed" in capsys.readouterr().out.lower()


class TestCmdProxy:
    def test_no_session_no_all(self, capsys):
        args = Namespace(all=False, session=None, sessions_dir=".", port=9222,
                         host="127.0.0.1", mode="cdp", legacy=False, no_gui=True,
                         visible=False, timeout=30, fingerprint=True, verbose=False,
                         auto_refresh=False, source_browser=None, source_profile=None,
                         impersonate=None, no_open_browser=True,
                         auto_navigate=False, target_url=None)
        cmd_proxy(args)
        assert "required" in capsys.readouterr().out.lower()

    def test_session_not_found(self, capsys):
        args = Namespace(all=False, session="/nonexistent/session.tokenade", sessions_dir=".", port=9222,
                         host="127.0.0.1", mode="cdp", legacy=False, no_gui=True,
                         visible=False, timeout=30, fingerprint=True, verbose=False,
                         auto_refresh=False, source_browser=None, source_profile=None,
                         impersonate=None, no_open_browser=True,
                         auto_navigate=False, target_url=None)
        cmd_proxy(args)
        assert "not found" in capsys.readouterr().out.lower()

    @patch("tokenade.core.proxy.multi_site_proxy.MultiSiteProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_all_mode_no_sessions(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        mock_packager = MagicMock()
        mock_packager_cls.return_value = mock_packager

        args = Namespace(all=True, session=None, sessions_dir=str(tmp_path), port=9222,
                         host="127.0.0.1", mode="cdp", legacy=False, no_gui=True,
                         visible=False, timeout=30, fingerprint=True, verbose=False,
                         auto_refresh=False, source_browser=None, source_profile=None,
                         impersonate=None, no_open_browser=True,
                         auto_navigate=False, target_url=None)
        cmd_proxy(args)
        assert "no session files" in capsys.readouterr().out.lower()

    @patch("tokenade.core.proxy.cdp_proxy.CDPProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    def test_cdp_mode(self, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = tmp_path / "session.tokenade"
        f.write_text(json.dumps({"cookies": [], "site_name": "test"}))
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": [], "site_name": "test"}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy_cls.from_session_file.return_value = mock_proxy

        args = Namespace(all=False, session=str(f), sessions_dir=".", port=9222,
                         host="127.0.0.1", mode="cdp", legacy=False, no_gui=True,
                         visible=False, timeout=30, fingerprint=True, verbose=False,
                         auto_refresh=False, source_browser=None, source_profile=None,
                         impersonate=None, no_open_browser=True,
                         auto_navigate=False, target_url=None)
        cmd_proxy(args)
        mock_proxy.run.assert_called_once()

    @patch("tokenade.core.proxy.forward_proxy.ForwardProxy")
    @patch("tokenade.core.importer.session_packager.SessionPackager")
    @patch("asyncio.run")
    def test_forward_mode(self, mock_run, mock_packager_cls, mock_proxy_cls, tmp_path, capsys):
        f = tmp_path / "session.tokenade"
        f.write_text(json.dumps({"cookies": [], "site_name": "test"}))
        mock_packager = MagicMock()
        mock_packager.load.return_value = {"cookies": [], "site_name": "test"}
        mock_packager_cls.return_value = mock_packager
        mock_proxy = MagicMock()
        mock_proxy_cls.return_value = mock_proxy

        args = Namespace(all=False, session=str(f), sessions_dir=".", port=9222,
                         host="127.0.0.1", mode="forward", legacy=False, no_gui=True,
                         visible=False, timeout=30, fingerprint=True, verbose=False,
                         auto_refresh=False, source_browser=None, source_profile=None,
                         impersonate=None, no_open_browser=True,
                         auto_navigate=False, target_url=None)
        cmd_proxy(args)
        mock_run.assert_called_once()
