"""Tests for tokenade.core.errors (mutation-oriented)."""

import pytest

from tokenade.core.errors import (
    TokenadeError,
    ExtractionError,
    InjectionError,
    EncryptionError,
    DecryptionError,
    DependencyError,
    PluginError,
)


def test_tokenade_error_stores_operation_and_cause():
    cause = RuntimeError("root")
    err = TokenadeError("boom", operation="export", cause=cause)
    assert err.operation == "export"
    assert err._cause is cause
    assert err.__cause__ is cause
    assert str(err) == "boom"


def test_tokenade_error_without_cause_leaves_dunder_cause_unset():
    err = TokenadeError("plain")
    assert err.operation is None
    assert err._cause is None
    assert err.__cause__ is None


def test_tokenade_error_operation_none_explicit():
    err = TokenadeError("x", operation=None)
    assert err.operation is None


def test_subclass_hierarchy():
    assert issubclass(ExtractionError, TokenadeError)
    assert issubclass(InjectionError, TokenadeError)
    assert issubclass(EncryptionError, TokenadeError)
    assert issubclass(DecryptionError, EncryptionError)
    assert issubclass(DecryptionError, ValueError)
    assert issubclass(DependencyError, TokenadeError)
    assert issubclass(PluginError, TokenadeError)


def test_decryption_error_is_value_error_for_compat():
    with pytest.raises(ValueError):
        raise DecryptionError("bad", operation="decrypt")
