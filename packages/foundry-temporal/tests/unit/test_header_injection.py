# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.header_injection module"""

from unittest.mock import AsyncMock, Mock

import pytest
from foundry_temporal._limits import MAX_HEADER_COUNT, MAX_HEADER_VALUE_LENGTH
from foundry_temporal.header_injection import (
    HeaderInjectionInterceptor,
    _OutboundInterceptor,
    outbound_headers,
)
from temporalio.api.common.v1 import Payload


class TestOutboundHeaders:
    def test_default_is_none(self):
        """ContextVar default is None (no headers)"""
        assert outbound_headers.get() is None

    def test_set_and_get(self):
        """Can set and retrieve headers from ContextVar"""
        token = outbound_headers.set({"x-identity-token": "abc123"})
        assert outbound_headers.get() == {"x-identity-token": "abc123"}
        outbound_headers.reset(token)

    def test_reset_to_none(self):
        """Reset clears back to None"""
        token = outbound_headers.set({"key": "val"})
        outbound_headers.reset(token)
        assert outbound_headers.get() is None


class TestOutboundInterceptor:
    @pytest.mark.asyncio
    async def test_injects_headers_when_present(self):
        """Headers from provider are encoded and merged into input.headers"""
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")

        def provider():
            return {"x-identity-token": "my-jwt", "x-request-id": "req-1"}

        interceptor = _OutboundInterceptor(mock_next, provider)

        mock_input = Mock()
        mock_input.headers = {}

        result = await interceptor.start_workflow(mock_input)

        assert result == "handle"
        assert "x-identity-token" in mock_input.headers
        assert "x-request-id" in mock_input.headers
        assert mock_input.headers["x-identity-token"].data == b"my-jwt"
        assert mock_input.headers["x-request-id"].data == b"req-1"

    @pytest.mark.asyncio
    async def test_preserves_existing_headers(self):
        """Existing headers on input are preserved when new headers are injected"""
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")

        def provider():
            return {"x-new": "new-val"}

        interceptor = _OutboundInterceptor(mock_next, provider)

        existing_payload = Payload(data=b"existing")
        mock_input = Mock()
        mock_input.headers = {"x-existing": existing_payload}

        await interceptor.start_workflow(mock_input)

        assert mock_input.headers["x-existing"] is existing_payload
        assert mock_input.headers["x-new"].data == b"new-val"

    @pytest.mark.asyncio
    async def test_no_injection_when_provider_returns_none(self):
        """No headers injected when provider returns None"""
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")

        def provider():
            return None

        interceptor = _OutboundInterceptor(mock_next, provider)

        mock_input = Mock()
        mock_input.headers = {"x-original": Payload(data=b"orig")}

        await interceptor.start_workflow(mock_input)

        assert mock_input.headers == {"x-original": Payload(data=b"orig")}

    @pytest.mark.asyncio
    async def test_no_injection_when_provider_returns_empty(self):
        """No headers injected when provider returns empty dict"""
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")

        def provider():
            return {}

        interceptor = _OutboundInterceptor(mock_next, provider)

        mock_input = Mock()
        mock_input.headers = {}

        await interceptor.start_workflow(mock_input)

        assert mock_input.headers == {}

    @pytest.mark.asyncio
    async def test_calls_next_start_workflow(self):
        """Always delegates to next interceptor"""
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="workflow-handle")

        def provider():
            return {"x-token": "t"}

        interceptor = _OutboundInterceptor(mock_next, provider)

        mock_input = Mock()
        mock_input.headers = {}

        result = await interceptor.start_workflow(mock_input)

        assert result == "workflow-handle"
        mock_next.start_workflow.assert_called_once_with(mock_input)

    # STIG V-222612: injected-header bounds

    @pytest.mark.asyncio
    async def test_rejects_too_many_headers(self):
        """More than MAX_HEADER_COUNT headers raises and does not start the workflow."""
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")

        def provider():
            return {f"h{i}": "v" for i in range(MAX_HEADER_COUNT + 1)}

        interceptor = _OutboundInterceptor(mock_next, provider)
        mock_input = Mock()
        mock_input.headers = {}

        with pytest.raises(ValueError, match="header count exceeds maximum"):
            await interceptor.start_workflow(mock_input)
        mock_next.start_workflow.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_oversized_header_value(self):
        """A header value over MAX_HEADER_VALUE_LENGTH raises and does not start the workflow."""
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")

        def provider():
            return {"x-identity-token": "j" * (MAX_HEADER_VALUE_LENGTH + 1)}

        interceptor = _OutboundInterceptor(mock_next, provider)
        mock_input = Mock()
        mock_input.headers = {}

        with pytest.raises(ValueError, match="exceeds maximum length"):
            await interceptor.start_workflow(mock_input)
        mock_next.start_workflow.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_headers_at_limits(self):
        """Headers at the count and value-length limits are injected normally."""
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")

        def provider():
            return {"x-identity-token": "j" * MAX_HEADER_VALUE_LENGTH}

        interceptor = _OutboundInterceptor(mock_next, provider)
        mock_input = Mock()
        mock_input.headers = {}

        await interceptor.start_workflow(mock_input)

        assert mock_input.headers["x-identity-token"].data == b"j" * MAX_HEADER_VALUE_LENGTH
        mock_next.start_workflow.assert_called_once_with(mock_input)


class TestHeaderInjectionInterceptor:
    def test_default_provider_uses_contextvar(self):
        """Default provider reads from outbound_headers ContextVar"""
        interceptor = HeaderInjectionInterceptor()
        # Built-in method objects aren't identity-comparable, so verify behavior
        token = outbound_headers.set({"x-test": "val"})
        assert interceptor._get_headers() == {"x-test": "val"}
        outbound_headers.reset(token)

    def test_custom_provider(self):
        """Custom provider is used instead of ContextVar"""

        def custom():
            return {"x-custom": "val"}

        interceptor = HeaderInjectionInterceptor(header_provider=custom)
        assert interceptor._get_headers is custom

    def test_intercept_client_returns_outbound_interceptor(self):
        """intercept_client wraps next with _OutboundInterceptor"""
        interceptor = HeaderInjectionInterceptor()
        mock_next = Mock()

        result = interceptor.intercept_client(mock_next)

        assert isinstance(result, _OutboundInterceptor)
        # Verify it uses the ContextVar provider by checking behavior
        token = outbound_headers.set({"x-check": "yes"})
        assert result._get_headers() == {"x-check": "yes"}
        outbound_headers.reset(token)

    def test_intercept_client_passes_custom_provider(self):
        """intercept_client passes custom provider to _OutboundInterceptor"""

        def custom():
            return {"x-custom": "val"}

        interceptor = HeaderInjectionInterceptor(header_provider=custom)
        mock_next = Mock()

        result = interceptor.intercept_client(mock_next)

        assert result._get_headers is custom
