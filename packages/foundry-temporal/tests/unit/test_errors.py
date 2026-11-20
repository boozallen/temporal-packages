# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.errors module"""

import errno
from unittest.mock import MagicMock

import pytest
from foundry_temporal.errors import (
    AgentError,
    ConfigurationError,
    NonRetryableError,
    RetryableError,
    StorageError,
    ValidationError,
    WorkflowError,
    classify_and_wrap_error,
    create_non_retryable_error,
    create_retryable_error,
    is_retryable_error,
)
from temporalio.exceptions import ApplicationError


class TestWorkflowError:
    def test_workflow_error_basic(self):
        """Test basic WorkflowError creation"""
        error = WorkflowError("test error")

        assert str(error) == "test error"
        assert isinstance(error, ApplicationError)
        assert error.non_retryable is True  # Default

    def test_workflow_error_retryable(self):
        """Test WorkflowError with non_retryable=False"""
        error = WorkflowError("test error", non_retryable=False)

        assert error.non_retryable is False

    def test_workflow_error_inheritance(self):
        """Test WorkflowError inheritance hierarchy"""
        error = WorkflowError("test")
        assert isinstance(error, ApplicationError)
        assert isinstance(error, Exception)


class TestRetryableError:
    def test_retryable_error_basic(self):
        """Test basic RetryableError creation"""
        error = RetryableError("retryable error")

        assert str(error) == "retryable error"
        assert isinstance(error, WorkflowError)
        assert error.non_retryable is False

    def test_retryable_error_inheritance(self):
        """Test RetryableError inheritance"""
        error = RetryableError("test")
        assert isinstance(error, WorkflowError)
        assert isinstance(error, ApplicationError)


class TestNonRetryableError:
    def test_non_retryable_error_basic(self):
        """Test basic NonRetryableError creation"""
        error = NonRetryableError("non-retryable error")

        assert str(error) == "non-retryable error"
        assert isinstance(error, WorkflowError)
        assert error.non_retryable is True

    def test_non_retryable_error_inheritance(self):
        """Test NonRetryableError inheritance"""
        error = NonRetryableError("test")
        assert isinstance(error, WorkflowError)
        assert isinstance(error, ApplicationError)


class TestSpecializedErrors:
    def test_agent_error(self):
        """Test AgentError"""
        error = AgentError("agent failed")
        assert isinstance(error, WorkflowError)
        assert str(error) == "agent failed"

    def test_storage_error(self):
        """Test StorageError"""
        error = StorageError("storage failed")
        assert isinstance(error, WorkflowError)
        assert str(error) == "storage failed"

    def test_configuration_error(self):
        """Test ConfigurationError"""
        error = ConfigurationError("config invalid")
        assert isinstance(error, NonRetryableError)
        assert isinstance(error, WorkflowError)
        assert error.non_retryable is True

    def test_validation_error(self):
        """Test ValidationError"""
        error = ValidationError("validation failed")
        assert isinstance(error, NonRetryableError)
        assert isinstance(error, WorkflowError)
        assert error.non_retryable is True


class TestIsRetryableError:
    def test_httpx_5xx_errors_retryable(self):
        """Test that HTTP 5xx errors are retryable"""
        pytest.importorskip("httpx")
        import httpx

        # Mock response with 500 status
        response = MagicMock()
        response.status_code = 500
        error = httpx.HTTPStatusError("Server error", request=None, response=response)

        assert is_retryable_error(error) is True

    def test_httpx_429_errors_retryable(self):
        """Test that HTTP 429 errors are retryable"""
        pytest.importorskip("httpx")
        import httpx

        # Mock response with 429 status
        response = MagicMock()
        response.status_code = 429
        error = httpx.HTTPStatusError("Rate limited", request=None, response=response)

        assert is_retryable_error(error) is True

    def test_httpx_4xx_errors_non_retryable(self):
        """Test that HTTP 4xx errors (except 429) are non-retryable"""
        pytest.importorskip("httpx")
        import httpx

        # Test various 4xx codes
        for status_code in [400, 401, 403, 404, 422]:
            response = MagicMock()
            response.status_code = status_code
            error = httpx.HTTPStatusError("Client error", request=None, response=response)

            assert is_retryable_error(error) is False, f"Status {status_code} should not be retryable"

    def test_httpx_timeout_retryable(self):
        """Test that HTTP timeout errors are retryable"""
        pytest.importorskip("httpx")
        import httpx

        error = httpx.TimeoutException("Request timed out")
        assert is_retryable_error(error) is True

    def test_httpx_connect_error_retryable(self):
        """Test that httpx.ConnectError is retryable"""
        pytest.importorskip("httpx")
        import httpx

        error = httpx.ConnectError("connection refused")
        assert is_retryable_error(error) is True

    def test_httpx_network_error_retryable(self):
        """Test that httpx.NetworkError subclasses are retryable"""
        pytest.importorskip("httpx")
        import httpx

        for err in [httpx.ReadError("read failed"), httpx.WriteError("write failed")]:
            assert is_retryable_error(err) is True

    def test_httpx_not_available(self):
        """Test error classification when httpx is not available"""

        # Mock an error that looks like HTTPStatusError but without httpx
        class FakeHTTPError(Exception):
            def __init__(self):
                self.response = MagicMock()
                self.response.status_code = 500

        error = FakeHTTPError()
        # Should not crash and should return False (unknown error type)
        assert is_retryable_error(error) is False

    def test_connection_error_retryable(self):
        """Test that ConnectionError is retryable"""
        error = ConnectionError("Connection failed")
        assert is_retryable_error(error) is True

    def test_os_error_file_not_found_non_retryable(self):
        """Test that file not found errors are non-retryable"""
        error = OSError()
        error.errno = errno.ENOENT  # File not found
        assert is_retryable_error(error) is False

    def test_os_error_permission_denied_non_retryable(self):
        """Test that permission denied errors are non-retryable"""
        error = OSError()
        error.errno = errno.EACCES  # Permission denied
        assert is_retryable_error(error) is False

    def test_os_error_other_retryable(self):
        """Test that other OS errors are retryable"""
        error = OSError()
        error.errno = errno.EAGAIN  # Resource temporarily unavailable
        assert is_retryable_error(error) is True

    def test_io_error_retryable(self):
        """Test that IOError follows same logic as OSError"""
        error = OSError()
        error.errno = errno.ENOENT
        assert is_retryable_error(error) is False

        error.errno = errno.EAGAIN
        assert is_retryable_error(error) is True

    def test_application_error_retryable_flag(self):
        """Test ApplicationError respects non_retryable flag"""
        retryable_error = ApplicationError("test", non_retryable=False)
        assert is_retryable_error(retryable_error) is True

        non_retryable_error = ApplicationError("test", non_retryable=True)
        assert is_retryable_error(non_retryable_error) is False

    def test_configuration_error_non_retryable(self):
        """Test that ConfigurationError is non-retryable"""
        error = ConfigurationError("config error")
        assert is_retryable_error(error) is False

    def test_validation_error_non_retryable(self):
        """Test that ValidationError is non-retryable"""
        error = ValidationError("validation error")
        assert is_retryable_error(error) is False

    def test_unknown_error_non_retryable(self):
        """Test that unknown errors default to non-retryable"""
        error = ValueError("unknown error")
        assert is_retryable_error(error) is False

    def test_retryable_workflow_errors(self):
        """Test that our custom retryable errors are detected correctly"""
        error = RetryableError("test")
        assert is_retryable_error(error) is True

    def test_non_retryable_workflow_errors(self):
        """Test that our custom non-retryable errors are detected correctly"""
        error = NonRetryableError("test")
        assert is_retryable_error(error) is False


class TestCreateRetryableError:
    def test_create_retryable_error_basic(self):
        """Test creating retryable error with message only"""
        error = create_retryable_error("test message")

        assert isinstance(error, RetryableError)
        assert str(error) == "test message"
        assert error.non_retryable is False

    def test_create_retryable_error_with_original(self):
        """Test creating retryable error with original error"""
        original = ValueError("original error")
        error = create_retryable_error("test message", original)

        assert isinstance(error, RetryableError)
        assert "test message: original error" in str(error)


class TestCreateNonRetryableError:
    def test_create_non_retryable_error_basic(self):
        """Test creating non-retryable error with message only"""
        error = create_non_retryable_error("test message")

        assert isinstance(error, NonRetryableError)
        assert str(error) == "test message"
        assert error.non_retryable is True

    def test_create_non_retryable_error_with_original(self):
        """Test creating non-retryable error with original error"""
        original = ValueError("original error")
        error = create_non_retryable_error("test message", original)

        assert isinstance(error, NonRetryableError)
        assert "test message: original error" in str(error)


class TestClassifyAndWrapError:
    def test_classify_retryable_error(self):
        """Test classifying and wrapping a retryable error"""
        original = ConnectionError("connection failed")
        wrapped = classify_and_wrap_error(original, "context")

        assert isinstance(wrapped, RetryableError)
        assert "context: connection failed" in str(wrapped)

    def test_classify_non_retryable_error(self):
        """Test classifying and wrapping a non-retryable error"""
        original = ValueError("invalid value")
        wrapped = classify_and_wrap_error(original, "context")

        assert isinstance(wrapped, NonRetryableError)
        assert "context: invalid value" in str(wrapped)

    def test_classify_without_context(self):
        """Test classifying error without context"""
        original = ValueError("test error")
        wrapped = classify_and_wrap_error(original)

        assert isinstance(wrapped, NonRetryableError)
        assert str(wrapped) == "test error"

    def test_classify_empty_context(self):
        """Test classifying error with empty context"""
        original = ValueError("test error")
        wrapped = classify_and_wrap_error(original, "")

        assert str(wrapped) == "test error"

    def test_classify_preserves_original_error(self):
        """Test that original error information is preserved"""
        original = ConnectionError("network issue")
        wrapped = classify_and_wrap_error(original, "API call failed")

        # Should be retryable because ConnectionError is retryable
        assert isinstance(wrapped, RetryableError)
        assert "API call failed: network issue" in str(wrapped)

    def test_classify_httpx_error(self):
        """Test classifying httpx errors"""
        httpx = pytest.importorskip("httpx")

        # 5xx error should be retryable
        response = MagicMock()
        response.status_code = 500
        original = httpx.HTTPStatusError("Server error", request=None, response=response)
        wrapped = classify_and_wrap_error(original, "API call")

        assert isinstance(wrapped, RetryableError)
        assert "API call" in str(wrapped)
