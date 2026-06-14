"""Tests for custom exception hierarchy."""

import pytest
from tokenade.core.errors import (
    TokenadeError,
    ExtractionError,
    InjectionError,
    EncryptionError,
    DecryptionError,
    SessionNotFoundError,
    BrowserNotFoundError,
    ProxyError,
    ConfigurationError,
    ValidationError,
    PluginError,
    NetworkError,
    FormatError,
)


class TestExceptionHierarchy:
    def test_base_exception(self):
        exc = TokenadeError("test error")
        assert str(exc) == "test error"
        assert exc.operation is None

    def test_base_with_operation(self):
        exc = TokenadeError("test", operation="export")
        assert exc.operation == "export"

    def test_base_with_cause(self):
        cause = ValueError("original")
        exc = TokenadeError("wrapped", cause=cause)
        assert exc.__cause__ is cause

    def test_extraction_error(self):
        exc = ExtractionError("failed", operation="extract")
        assert isinstance(exc, TokenadeError)
        assert exc.operation == "extract"

    def test_injection_error(self):
        exc = InjectionError("failed")
        assert isinstance(exc, TokenadeError)

    def test_encryption_error(self):
        exc = EncryptionError("failed")
        assert isinstance(exc, TokenadeError)

    def test_decryption_error_is_encryption_error(self):
        exc = DecryptionError("wrong password")
        assert isinstance(exc, EncryptionError)
        assert isinstance(exc, TokenadeError)

    def test_decryption_error_is_value_error(self):
        exc = DecryptionError("wrong password")
        assert isinstance(exc, ValueError)

    def test_session_not_found(self):
        exc = SessionNotFoundError("not found")
        assert isinstance(exc, TokenadeError)

    def test_browser_not_found(self):
        exc = BrowserNotFoundError("not found")
        assert isinstance(exc, TokenadeError)

    def test_proxy_error(self):
        exc = ProxyError("proxy failed")
        assert isinstance(exc, TokenadeError)

    def test_configuration_error(self):
        exc = ConfigurationError("invalid config")
        assert isinstance(exc, TokenadeError)

    def test_validation_error(self):
        exc = ValidationError("invalid")
        assert isinstance(exc, TokenadeError)

    def test_plugin_error(self):
        exc = PluginError("plugin failed")
        assert isinstance(exc, TokenadeError)

    def test_network_error(self):
        exc = NetworkError("connection refused")
        assert isinstance(exc, TokenadeError)

    def test_format_error(self):
        exc = FormatError("invalid format")
        assert isinstance(exc, TokenadeError)

    def test_catch_base_catches_all(self):
        with pytest.raises(TokenadeError):
            raise ExtractionError("test")

    def test_catch_encryption_catches_decryption(self):
        with pytest.raises(EncryptionError):
            raise DecryptionError("test")

    def test_backward_compat_value_error(self):
        with pytest.raises(ValueError):
            raise DecryptionError("test")
