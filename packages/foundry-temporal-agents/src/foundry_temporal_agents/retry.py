# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Network Retry Logic Specific to Strands

Strands-specific retry policies that handle network conditions, agent availability,
and A2A protocol specifics based on foundry-temporal architecture specifications.
"""

from datetime import timedelta

from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from .exceptions import AgentNotFoundError, AgentRequestError, AgentTimeoutError

# Strands Agent Network Retry Policies
# These are tuned for network conditions and agent response patterns

# Standard agent call with network-aware retry
STRANDS_AGENT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
    backoff_coefficient=2.0,
)

# Long-running agent operations (research, analysis)
STRANDS_LONG_OPERATION_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
    backoff_coefficient=1.5,
)

# Quick agent operations (health checks, simple queries)
STRANDS_QUICK_OPERATION_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
    backoff_coefficient=2.0,
)

# Agent discovery and capability checking
STRANDS_DISCOVERY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=5),
    maximum_attempts=4,
    backoff_coefficient=1.8,
)

# A2A protocol handshake retry
STRANDS_A2A_HANDSHAKE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(milliseconds=500),
    maximum_interval=timedelta(seconds=8),
    maximum_attempts=6,
    backoff_coefficient=2.2,
)

# MCP server communication retry (when agent uses MCP)
STRANDS_MCP_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=15),
    maximum_attempts=4,
    backoff_coefficient=2.0,
)


# Non-retryable errors for Strands operations
STRANDS_NON_RETRYABLE_ERRORS = {
    "agent_not_found",  # Agent doesn't exist
    "invalid_capability",  # Agent can't handle request type
    "authentication_failed",  # Auth credentials invalid
    "malformed_request",  # Request format invalid
    "resource_limit_exceeded",  # Agent resource limits hit
}


def get_strands_retry_policy(operation_type: str = "default") -> RetryPolicy:
    """
    Get appropriate retry policy for different Strands operation types

    Args:
        operation_type: Type of operation ("default", "long", "quick", "discovery", "a2a", "mcp")

    Returns:
        RetryPolicy: Appropriate policy for the operation type
    """
    policies = {
        "default": STRANDS_AGENT_RETRY_POLICY,
        "long": STRANDS_LONG_OPERATION_RETRY_POLICY,
        "quick": STRANDS_QUICK_OPERATION_RETRY_POLICY,
        "discovery": STRANDS_DISCOVERY_RETRY_POLICY,
        "a2a": STRANDS_A2A_HANDSHAKE_RETRY_POLICY,
        "mcp": STRANDS_MCP_RETRY_POLICY,
    }

    return policies.get(operation_type, STRANDS_AGENT_RETRY_POLICY)


_RETRYABLE_4XX_STATUSES = frozenset({408, 429})


def is_non_retryable_http_status(status: int) -> bool:
    """
    Classify a raw HTTP response status code from an agent as retryable or not.

    Used by both StrandsAgentClient and StrandsQueryClient during their own
    request retry loops, so a 4xx (client error) is not retried and a 5xx
    (server error) is retried the same way in both clients. 408 (Request
    Timeout) and 429 (Too Many Requests) are transient and stay retryable.

    Args:
        status: HTTP status code from the agent's response.

    Returns:
        bool: True if the status is a 4xx client error (not retryable).
    """
    return 400 <= status < 500 and status not in _RETRYABLE_4XX_STATUSES


def is_retryable_strands_error(error: Exception) -> bool:
    """
    Determine if a Strands-related error should be retried

    Args:
        error: Exception that occurred during Strands operation

    Returns:
        bool: True if error is retryable, False otherwise
    """
    # Application errors with specific non-retryable types
    if isinstance(error, ApplicationError):
        error_type = getattr(error, "type", "")
        if error_type in STRANDS_NON_RETRYABLE_ERRORS:
            return False

    # Specific Strands exceptions
    if isinstance(error, AgentNotFoundError):
        # Only a 404 is permanent. Unreachable agents and 408/429/5xx may recover.
        return error.status != 404

    if isinstance(error, AgentRequestError):
        return False  # The agent rejected the request with a 4xx

    if isinstance(error, AgentTimeoutError):
        return True  # Timeout could be transient network issue

    # Network-related errors are generally retryable
    if "ConnectionError" in str(type(error)):
        return True

    if "TimeoutError" in str(type(error)):
        return True

    if "NetworkError" in str(type(error)):
        return True

    # HTTP status code based decisions
    if hasattr(error, "status_code"):
        status_code = error.status_code  # type: ignore[attr-defined]

        # 4xx client errors (except 408, 429) are generally not retryable
        if 400 <= status_code < 500:
            if status_code in [408, 429]:  # Request Timeout, Too Many Requests
                return True
            return False

        # 5xx server errors are retryable
        if 500 <= status_code < 600:
            return True

    # Default to retryable for unknown errors
    return True


def create_strands_retry_policy(
    operation_type: str = "default",
    max_attempts: int | None = None,
    max_interval: timedelta | None = None,
    initial_interval: timedelta | None = None,
    backoff_coefficient: float | None = None,
) -> RetryPolicy:
    """
    Create custom Strands retry policy with overrides

    Args:
        operation_type: Base policy type to start from
        max_attempts: Override maximum attempts
        max_interval: Override maximum interval
        initial_interval: Override initial interval
        backoff_coefficient: Override backoff coefficient

    Returns:
        RetryPolicy: Custom retry policy
    """
    base_policy = get_strands_retry_policy(operation_type)

    return RetryPolicy(
        initial_interval=initial_interval or base_policy.initial_interval,
        maximum_interval=max_interval or base_policy.maximum_interval,
        maximum_attempts=max_attempts or base_policy.maximum_attempts,
        backoff_coefficient=backoff_coefficient or base_policy.backoff_coefficient,
    )


# Retry policy mapping for different Strands agent operations
OPERATION_RETRY_POLICIES: dict[str, RetryPolicy] = {
    # Agent communication patterns
    "agent_call": STRANDS_AGENT_RETRY_POLICY,
    "agent_health_check": STRANDS_QUICK_OPERATION_RETRY_POLICY,
    "agent_capability_check": STRANDS_DISCOVERY_RETRY_POLICY,
    # Workflow-specific operations
    "research_task": STRANDS_LONG_OPERATION_RETRY_POLICY,
    "analysis_task": STRANDS_LONG_OPERATION_RETRY_POLICY,
    "planning_task": STRANDS_AGENT_RETRY_POLICY,
    "feedback_incorporation": STRANDS_AGENT_RETRY_POLICY,
    # Protocol operations
    "a2a_handshake": STRANDS_A2A_HANDSHAKE_RETRY_POLICY,
    "mcp_operation": STRANDS_MCP_RETRY_POLICY,
    # Quick operations
    "status_query": STRANDS_QUICK_OPERATION_RETRY_POLICY,
    "simple_query": STRANDS_QUICK_OPERATION_RETRY_POLICY,
}


def get_operation_retry_policy(operation_name: str) -> RetryPolicy:
    """
    Get retry policy for specific Strands agent operation

    Args:
        operation_name: Name of the operation

    Returns:
        RetryPolicy: Appropriate retry policy
    """
    return OPERATION_RETRY_POLICIES.get(operation_name, STRANDS_AGENT_RETRY_POLICY)
