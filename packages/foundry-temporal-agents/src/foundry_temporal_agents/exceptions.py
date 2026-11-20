# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Strands-specific exceptions for Temporal workflows
"""


class StrandsAgentError(Exception):
    """Base exception for all Strands agent errors"""

    pass


class AgentNotFoundError(StrandsAgentError):
    """Agent discovery failed - agent not found or unreachable"""

    def __init__(self, agent_url: str, original_error: Exception | None = None, status: int | None = None):
        self.agent_url = agent_url
        self.original_error = original_error
        # HTTP status when the agent answered (e.g. 404); None when unreachable.
        self.status = status
        if status is None or status == 404:
            super().__init__(f"Agent not found at {agent_url}")
        else:
            super().__init__(f"Agent at {agent_url} failed with HTTP {status}")


class AgentUnavailableError(AgentNotFoundError):
    """Agent answered with a transient HTTP status (408, 429 or 5xx); retryable.

    Subclasses AgentNotFoundError so existing `except AgentNotFoundError` handlers still catch it.
    """


class AgentAuthenticationError(StrandsAgentError):
    """Agent rejected the request as unauthenticated/unauthorized (401/403)."""

    def __init__(self, agent_url: str, status_code: int):
        self.agent_url = agent_url
        self.status_code = status_code
        super().__init__(f"Agent authentication failed ({status_code}) at {agent_url}")


class AgentTimeoutError(StrandsAgentError):
    """Agent response timeout"""

    def __init__(self, agent_url: str, timeout_seconds: int):
        self.agent_url = agent_url
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Agent timeout after {timeout_seconds}s: {agent_url}")


class A2AProtocolError(StrandsAgentError):
    """A2A protocol error - malformed request or response"""

    def __init__(self, message: str, response_data: dict | None = None):
        self.response_data = response_data
        super().__init__(message)


class AgentCapabilityError(StrandsAgentError):
    """Agent doesn't support the requested capability"""

    def __init__(self, agent_name: str, capability: str, available_capabilities: list | None = None):
        self.agent_name = agent_name
        self.capability = capability
        self.available_capabilities = available_capabilities or []
        super().__init__(f"Agent '{agent_name}' does not support required capability: {capability}")


class QueryProcessingError(StrandsAgentError):
    """Query processing error - malformed request or processing failure"""

    def __init__(self, message: str, context: dict | None = None, retryable: bool = True):
        self.context = context or {}
        self.retryable = retryable
        super().__init__(message)


class InputBoundsError(ValueError):
    """Activity input exceeds a STIG V-222612 size, length or range bound.

    A ``ValueError`` subclass, so existing ``except ValueError`` handlers still
    catch it. Workflow code that builds an oversized ``StrandsAgentTaskInput``
    raises it directly, and Temporal treats a plain exception in workflow code as
    a workflow task failure that retries indefinitely. List it in the worker's
    ``workflow_failure_exception_types`` to fail the workflow instead.
    """


class AgentRequestError(StrandsAgentError):
    """Agent rejected the request with a non-retryable HTTP status (e.g. a 4xx)"""

    def __init__(self, agent_url: str, status: int, original_error: Exception | None = None):
        self.agent_url = agent_url
        self.status = status
        self.original_error = original_error
        super().__init__(f"Agent rejected request to {agent_url}: HTTP {status}")
