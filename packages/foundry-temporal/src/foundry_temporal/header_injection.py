# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Client interceptor for injecting headers into Temporal workflow starts.

Sets headers on outbound start_workflow calls. Headers are resolved via a
provider callable — by default a ContextVar (ideal for async web frameworks),
but callers can supply any function that returns a dict of headers.

Pairs with HeaderPropagationInterceptor (worker-side) which propagates those
headers from workflow start into activity execution context.

Supports optional Fernet encryption of header values so that JWTs and other
sensitive data are not stored in base64 in Temporal's workflow event history.
"""

import contextvars
import logging
from collections.abc import Callable
from typing import Any

from temporalio.api.common.v1 import Payload
from temporalio.client import (
    Interceptor,
    OutboundInterceptor,
    StartWorkflowInput,
    WorkflowHandle,
)

from ._limits import enforce_header_bounds

logger = logging.getLogger(__name__)

outbound_headers: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "outbound_headers", default=None
)


class _OutboundInterceptor(OutboundInterceptor):
    def __init__(
        self,
        next: OutboundInterceptor,
        get_headers: Callable[[], dict[str, str] | None],
        fernet: Any = None,
    ) -> None:
        super().__init__(next)
        self._get_headers = get_headers
        self._fernet = fernet

    async def start_workflow(self, input: StartWorkflowInput) -> WorkflowHandle[Any, Any]:
        headers = self._get_headers()
        logger.debug(
            "HeaderInjectionInterceptor.start_workflow fired, headers=%s",
            list(headers.keys()) if headers else "EMPTY",
        )
        if headers:
            # STIG V-222612: reject oversized header payloads before they enter
            # the workflow start / event history.
            enforce_header_bounds(headers)
            input.headers = {
                **input.headers,
                **{
                    k: Payload(data=self._fernet.encrypt(v.encode("utf-8")) if self._fernet else v.encode("utf-8"))
                    for k, v in headers.items()
                },
            }
        return await self.next.start_workflow(input)


class HeaderInjectionInterceptor(Interceptor):
    """Client interceptor that injects headers into workflow start calls.

    Args:
        header_provider: Callable that returns headers to inject. Defaults to
            reading from the outbound_headers ContextVar.
        encryption_key: Fernet key for encryption. If provided, header values
            are encrypted before being stored in workflow event history.

    Usage (web app with ContextVar):
        from foundry_temporal import HeaderInjectionInterceptor, outbound_headers

        client = await Client.connect(..., interceptors=[HeaderInjectionInterceptor()])

        # In a route handler
        outbound_headers.set({"x-identity-token": token})
        await client.start_workflow(...)

    Usage (with encryption):
        interceptor = HeaderInjectionInterceptor(
            encryption_key=os.environ.get("HEADER_ENCRYPTION_KEY")
        )
        client = await Client.connect(..., interceptors=[interceptor])
    """

    def __init__(
        self,
        header_provider: Callable[[], dict[str, str] | None] | None = None,
        encryption_key: str | bytes | None = None,
    ):
        self._get_headers = header_provider or outbound_headers.get
        if encryption_key:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(encryption_key)
        else:
            self._fernet = None

    def intercept_client(self, next: OutboundInterceptor) -> OutboundInterceptor:
        return _OutboundInterceptor(next, self._get_headers, self._fernet)
