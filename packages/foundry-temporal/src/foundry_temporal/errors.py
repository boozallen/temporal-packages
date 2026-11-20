# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Standard Error Types and Handlers

Error classification based on foundry-temporal architecture specifications.
"""

from temporalio.exceptions import ApplicationError


class WorkflowError(ApplicationError):
    """Base class for workflow-specific errors"""

    def __init__(self, message: str, non_retryable: bool = True):
        super().__init__(message, non_retryable=non_retryable)


class RetryableError(WorkflowError):
    """Errors that should be retried by Temporal"""

    def __init__(self, message: str):
        super().__init__(message, non_retryable=False)


class NonRetryableError(WorkflowError):
    """Errors that should not be retried"""

    def __init__(self, message: str):
        super().__init__(message, non_retryable=True)


class AgentError(WorkflowError):
    """Agent-specific errors"""

    pass


class StorageError(WorkflowError):
    """Storage operation errors"""

    pass


class ConfigurationError(NonRetryableError):
    """Configuration and setup errors"""

    pass


class ValidationError(NonRetryableError):
    """Input validation errors"""

    pass


# Error classification functions
def is_retryable_error(error: Exception) -> bool:
    """
    Classify if an error should be retried by Temporal

    Based on architecture specification:
    Retryable Errors:
    - httpx.HTTPStatusError (5xx, 429)
    - httpx.TimeoutException
    - ConnectionError
    - Transient file system errors

    Non-Retryable Errors:
    - ApplicationError(non_retryable=True)
    - Invalid input data
    - Agent protocol errors (4xx)
    - Missing configuration
    """

    # HTTP errors - only retry 5xx and 429 (lazy import)
    try:
        import httpx

        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code >= 500 or error.response.status_code == 429
        if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
            return True
    except ImportError:
        pass

    # Network and timeout errors - retryable
    if isinstance(error, ConnectionError):
        return True

    # File system errors (basic heuristic)
    if isinstance(error, (OSError, IOError)):
        # Retry permission and temporary errors, not "file not found"
        return error.errno not in (2, 13)  # ENOENT, EACCES

    # Application errors with explicit non_retryable flag
    if isinstance(error, ApplicationError):
        return not error.non_retryable

    # Configuration and validation errors - never retry
    if isinstance(error, (ConfigurationError, ValidationError)):
        return False

    # Unknown errors - default to non-retryable for safety
    return False


def create_retryable_error(message: str, original_error: Exception | None = None) -> RetryableError:
    """Create a retryable error with optional original error context"""
    if original_error:
        message = f"{message}: {str(original_error)}"
    return RetryableError(message)


def create_non_retryable_error(message: str, original_error: Exception | None = None) -> NonRetryableError:
    """Create a non-retryable error with optional original error context"""
    if original_error:
        message = f"{message}: {str(original_error)}"
    return NonRetryableError(message)


def classify_and_wrap_error(error: Exception, context: str = "") -> RetryableError | NonRetryableError:
    """
    Classify an exception and wrap it in the appropriate Temporal error type

    Args:
        error: The original exception
        context: Additional context for the error message

    Returns:
        Either RetryableError or NonRetryableError based on classification
    """
    base_message = f"{context}: {str(error)}" if context else str(error)

    if is_retryable_error(error):
        return RetryableError(base_message)
    else:
        return NonRetryableError(base_message)
