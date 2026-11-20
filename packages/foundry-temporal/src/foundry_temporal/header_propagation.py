# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Generic header propagation for Temporal workflows.

Propagates headers attached at workflow start into activity execution context.
Activities can read any propagated header via get_header() or get_propagated_headers().

The interceptor works in two stages:
1. Workflow interceptor captures headers from workflow start and copies them
   to every scheduled activity (Temporal does NOT do this automatically).
2. Activity interceptor decodes those headers and exposes them via context var.

Supports optional Fernet decryption of header values when paired with
HeaderInjectionInterceptor's encrypt mode.
"""

import contextvars
import logging
from typing import Any

from temporalio.api.common.v1 import Payload
from temporalio.worker import (
    ActivityInboundInterceptor,
    ExecuteActivityInput,
    Interceptor,
    WorkflowInboundInterceptor,
    WorkflowOutboundInterceptor,
)
from temporalio.worker._interceptor import (
    ExecuteWorkflowInput,
    StartActivityInput,
    StartLocalActivityInput,
    WorkflowInterceptorClassInput,
)

logger = logging.getLogger(__name__)

_propagated_headers: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "propagated_headers", default=None
)


def get_propagated_headers() -> dict[str, str]:
    """Get all propagated headers inside an activity."""
    return _propagated_headers.get() or {}


def get_header(key: str) -> str | None:
    """Get a single propagated header by key inside an activity."""
    headers = _propagated_headers.get()
    if headers is None:
        return None
    return headers.get(key)


class _WorkflowOutbound(WorkflowOutboundInterceptor):
    """Copies workflow-start headers to every outbound activity call."""

    def __init__(self, next: WorkflowOutboundInterceptor, inbound: _WorkflowInbound) -> None:
        super().__init__(next)
        self._inbound = inbound

    def start_activity(self, input: StartActivityInput) -> Any:
        logger.debug(
            "WorkflowOutbound.start_activity propagating headers=%s",
            list(self._inbound._headers.keys()) if self._inbound._headers else "EMPTY",
        )
        if self._inbound._headers:
            input.headers = {**input.headers, **self._inbound._headers}
        return self.next.start_activity(input)

    def start_local_activity(self, input: StartLocalActivityInput) -> Any:
        if self._inbound._headers:
            input.headers = {**input.headers, **self._inbound._headers}
        return self.next.start_local_activity(input)


class _WorkflowInbound(WorkflowInboundInterceptor):
    """Captures headers from workflow start for later propagation."""

    def __init__(self, next: WorkflowInboundInterceptor) -> None:
        super().__init__(next)
        self._headers: dict[str, Payload] = {}

    def init(self, outbound: WorkflowOutboundInterceptor) -> None:
        self.next.init(_WorkflowOutbound(outbound, self))

    async def execute_workflow(self, input: ExecuteWorkflowInput) -> Any:
        self._headers = dict(input.headers) if input.headers else {}
        logger.debug(
            "WorkflowInbound.execute_workflow headers=%s",
            list(self._headers.keys()) if self._headers else "EMPTY",
        )
        return await self.next.execute_workflow(input)


class _ActivityInterceptor(ActivityInboundInterceptor):
    """Decodes propagated headers and exposes them via context var."""

    def __init__(self, next: ActivityInboundInterceptor, fernet: Any = None) -> None:
        super().__init__(next)
        self._fernet = fernet

    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        headers = {}
        for k, v in (input.headers or {}).items():
            data = self._fernet.decrypt(v.data) if self._fernet else v.data
            headers[k] = data.decode("utf-8")
        _propagated_headers.set(headers)
        try:
            return await self.next.execute_activity(input)
        finally:
            _propagated_headers.set({})


class HeaderPropagationInterceptor(Interceptor):
    """Worker interceptor that propagates workflow-start headers to activities.

    Handles two interception points:
    - Workflow: captures start headers, copies them to scheduled activities
    - Activity: decodes headers into a context var for application code

    Args:
        encryption_key: Fernet key for decryption. If provided, header values
            are decrypted before being exposed to activity code.
    """

    def __init__(
        self,
        encryption_key: str | bytes | None = None,
    ):
        if encryption_key:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(encryption_key)
        else:
            self._fernet = None

    def intercept_activity(self, next: ActivityInboundInterceptor) -> ActivityInboundInterceptor:
        return _ActivityInterceptor(next, self._fernet)

    def workflow_interceptor_class(
        self, input: WorkflowInterceptorClassInput
    ) -> type[WorkflowInboundInterceptor] | None:
        return _WorkflowInbound
