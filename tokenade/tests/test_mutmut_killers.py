"""Targeted tests that kill known mutmut survivors on high-value modules.

These exist because return-type-only tests miss alias / default / side-effect
mutations (e.g. fallback still returns GoogleHandler).
"""

from __future__ import annotations

import logging
from typing import Optional

import pytest

from tokenade.core.crypto import encryptor as encryptor_mod
from tokenade.core.crypto.encryptor import MAGIC, TokenadeEncryptor
from tokenade.core.errors import TokenadeError
from tokenade.handlers.base import HandlerRegistry, SiteHandler
from tokenade.handlers.resolve import resolve_legacy_handler_class


class _UniqueGoogle(SiteHandler):
    SITE_NAME = "google"

    def check_auth_status(self):
        raise NotImplementedError

    def extract_tokens(self):
        return []

    def extract_cookies(self):
        return []


class _UniqueChatGPT(SiteHandler):
    SITE_NAME = "chatgpt"

    def check_auth_status(self):
        raise NotImplementedError

    def extract_tokens(self):
        return []

    def extract_cookies(self):
        return []


class _UniqueGitHub(SiteHandler):
    SITE_NAME = "github"

    def check_auth_status(self):
        raise NotImplementedError

    def extract_tokens(self):
        return []

    def extract_cookies(self):
        return []


@pytest.fixture
def isolated_registry():
    """Swap HandlerRegistry contents; restore after test."""
    prev = dict(HandlerRegistry._handlers)
    HandlerRegistry._handlers.clear()
    HandlerRegistry._handlers["google"] = _UniqueGoogle
    HandlerRegistry._handlers["chatgpt"] = _UniqueChatGPT
    HandlerRegistry._handlers["github"] = _UniqueGitHub
    yield
    HandlerRegistry._handlers.clear()
    HandlerRegistry._handlers.update(prev)


class TestResolveAliasAndRegistryKillers:
    def test_default_none_uses_google_registry_key(self, isolated_registry):
        # Mutant: site_name or "XXgoogleXX" → would miss registry and fall back
        assert resolve_legacy_handler_class(None) is _UniqueGoogle
        assert resolve_legacy_handler_class("") is _UniqueGoogle

    def test_gmail_and_youtube_alias_to_google_registry(self, isolated_registry):
        assert resolve_legacy_handler_class("gmail") is _UniqueGoogle
        assert resolve_legacy_handler_class("youtube") is _UniqueGoogle
        assert resolve_legacy_handler_class("GMail") is _UniqueGoogle
        assert resolve_legacy_handler_class("  youtube  ") is _UniqueGoogle

    def test_openai_alias_to_chatgpt_registry(self, isolated_registry):
        assert resolve_legacy_handler_class("openai") is _UniqueChatGPT

    def test_registry_hit_preferred_over_fallback(self, isolated_registry):
        # Mutant: registered = None always → would return None
        assert resolve_legacy_handler_class("google") is _UniqueGoogle


class TestEncryptorConstantKillers:
    def test_magic_exact_bytes(self):
        # Mutant: MAGIC = b'XXTOKENADE_ENCRYPTEDXX' still round-trips with itself
        assert MAGIC == b"TOKENADE_ENCRYPTED"
        assert encryptor_mod.MAGIC == b"TOKENADE_ENCRYPTED"

    def test_logger_is_module_logger(self):
        # Mutant: logger = None → encrypt_file would blow up; also assert identity
        assert encryptor_mod.logger is not None
        assert isinstance(encryptor_mod.logger, logging.Logger)
        assert encryptor_mod.logger.name == "tokenade.core.crypto.encryptor"

    def test_encrypt_file_uses_logger(self, tmp_path):
        enc = TokenadeEncryptor()
        src = tmp_path / "plain.bin"
        dst = tmp_path / "out.enc"
        src.write_bytes(b"payload")
        # Survives only if logger is a real Logger (logger=None → AttributeError)
        out = enc.encrypt_file(str(src), str(dst), "pw")
        assert out == str(dst)
        assert dst.read_bytes()[: len(MAGIC)] == MAGIC


class TestErrorsAttributeKillers:
    def test_operation_and_cause_not_nulled(self):
        cause = ValueError("inner")
        err = TokenadeError("outer", operation="inject", cause=cause)
        # Mutants set these to None unconditionally
        assert err.operation == "inject"
        assert err._cause is cause
        assert err.__cause__ is cause
