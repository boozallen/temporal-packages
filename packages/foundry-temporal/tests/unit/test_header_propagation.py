# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.header_propagation module"""

from unittest.mock import AsyncMock, Mock

import pytest
from foundry_temporal.header_propagation import (
    HeaderPropagationInterceptor,
    _ActivityInterceptor,
    _propagated_headers,
    _WorkflowInbound,
    _WorkflowOutbound,
    get_header,
    get_propagated_headers,
)
from temporalio.api.common.v1 import Payload


class TestGetPropagatedHeaders:
    def test_returns_empty_dict_when_none(self):
        """Returns empty dict when ContextVar is None (default)"""
        token = _propagated_headers.set(None)
        try:
            assert get_propagated_headers() == {}
        finally:
            _propagated_headers.reset(token)

    def test_returns_headers_when_set(self):
        """Returns headers dict when ContextVar has a value"""
        token = _propagated_headers.set({"x-identity-token": "jwt123", "x-request-id": "req-1"})
        try:
            assert get_propagated_headers() == {"x-identity-token": "jwt123", "x-request-id": "req-1"}
        finally:
            _propagated_headers.reset(token)

    def test_returns_empty_dict_when_empty(self):
        """Returns empty dict when ContextVar is empty dict"""
        token = _propagated_headers.set({})
        try:
            assert get_propagated_headers() == {}
        finally:
            _propagated_headers.reset(token)


class TestGetHeader:
    def test_returns_value_when_key_exists(self):
        """Returns header value for existing key"""
        token = _propagated_headers.set({"x-identity-token": "jwt123"})
        try:
            assert get_header("x-identity-token") == "jwt123"
        finally:
            _propagated_headers.reset(token)

    def test_returns_none_when_key_missing(self):
        """Returns None when key not in headers"""
        token = _propagated_headers.set({"x-identity-token": "jwt123"})
        try:
            assert get_header("x-nonexistent") is None
        finally:
            _propagated_headers.reset(token)

    def test_returns_none_when_contextvar_is_none(self):
        """Returns None when ContextVar is None (not in activity context)"""
        token = _propagated_headers.set(None)
        try:
            assert get_header("x-identity-token") is None
        finally:
            _propagated_headers.reset(token)


class TestWorkflowOutbound:
    def test_start_activity_propagates_headers(self):
        """Copies inbound headers to activity start input"""
        mock_next = Mock()
        mock_next.start_activity = Mock(return_value="activity-handle")

        mock_inbound = Mock()
        mock_inbound._headers = {
            "x-identity-token": Payload(data=b"jwt123"),
            "x-request-id": Payload(data=b"req-1"),
        }

        outbound = _WorkflowOutbound(mock_next, mock_inbound)

        mock_input = Mock()
        mock_input.headers = {}

        result = outbound.start_activity(mock_input)

        assert result == "activity-handle"
        assert mock_input.headers["x-identity-token"].data == b"jwt123"
        assert mock_input.headers["x-request-id"].data == b"req-1"

    def test_start_activity_preserves_existing_headers(self):
        """Existing activity headers are preserved"""
        mock_next = Mock()
        mock_next.start_activity = Mock(return_value="handle")

        mock_inbound = Mock()
        mock_inbound._headers = {"x-new": Payload(data=b"new")}

        outbound = _WorkflowOutbound(mock_next, mock_inbound)

        existing = Payload(data=b"existing")
        mock_input = Mock()
        mock_input.headers = {"x-existing": existing}

        outbound.start_activity(mock_input)

        assert mock_input.headers["x-existing"] is existing
        assert mock_input.headers["x-new"].data == b"new"

    def test_start_activity_no_headers(self):
        """Does not modify input when inbound has no headers"""
        mock_next = Mock()
        mock_next.start_activity = Mock(return_value="handle")

        mock_inbound = Mock()
        mock_inbound._headers = {}

        outbound = _WorkflowOutbound(mock_next, mock_inbound)

        mock_input = Mock()
        mock_input.headers = {"x-original": Payload(data=b"orig")}

        outbound.start_activity(mock_input)

        assert mock_input.headers == {"x-original": Payload(data=b"orig")}

    def test_start_local_activity_propagates_headers(self):
        """Copies inbound headers to local activity start input"""
        mock_next = Mock()
        mock_next.start_local_activity = Mock(return_value="local-handle")

        mock_inbound = Mock()
        mock_inbound._headers = {"x-token": Payload(data=b"tok")}

        outbound = _WorkflowOutbound(mock_next, mock_inbound)

        mock_input = Mock()
        mock_input.headers = {}

        result = outbound.start_local_activity(mock_input)

        assert result == "local-handle"
        assert mock_input.headers["x-token"].data == b"tok"

    def test_start_local_activity_no_headers(self):
        """Does not modify local activity input when no headers"""
        mock_next = Mock()
        mock_next.start_local_activity = Mock(return_value="handle")

        mock_inbound = Mock()
        mock_inbound._headers = {}

        outbound = _WorkflowOutbound(mock_next, mock_inbound)

        mock_input = Mock()
        mock_input.headers = {}

        outbound.start_local_activity(mock_input)

        assert mock_input.headers == {}


class TestWorkflowInbound:
    @pytest.mark.asyncio
    async def test_execute_workflow_captures_headers(self):
        """Captures headers from workflow start input"""
        mock_next = Mock()
        mock_next.execute_workflow = AsyncMock(return_value="wf-result")
        mock_next.init = Mock()

        inbound = _WorkflowInbound(mock_next)

        mock_input = Mock()
        mock_input.headers = {
            "x-identity-token": Payload(data=b"jwt"),
            "x-request-id": Payload(data=b"req"),
        }

        result = await inbound.execute_workflow(mock_input)

        assert result == "wf-result"
        assert inbound._headers == {
            "x-identity-token": Payload(data=b"jwt"),
            "x-request-id": Payload(data=b"req"),
        }

    @pytest.mark.asyncio
    async def test_execute_workflow_no_headers(self):
        """Handles None headers gracefully"""
        mock_next = Mock()
        mock_next.execute_workflow = AsyncMock(return_value="result")
        mock_next.init = Mock()

        inbound = _WorkflowInbound(mock_next)

        mock_input = Mock()
        mock_input.headers = None

        await inbound.execute_workflow(mock_input)

        assert inbound._headers == {}

    def test_init_wraps_outbound(self):
        """init() wraps outbound with _WorkflowOutbound"""
        mock_next = Mock()
        mock_next.init = Mock()

        inbound = _WorkflowInbound(mock_next)

        mock_outbound = Mock()
        inbound.init(mock_outbound)

        call_args = mock_next.init.call_args[0]
        assert isinstance(call_args[0], _WorkflowOutbound)


class TestActivityInterceptor:
    @pytest.mark.asyncio
    async def test_decodes_headers_into_contextvar(self):
        """Decodes Payload headers and sets ContextVar"""
        mock_next = Mock()

        captured = {}

        async def capture_execute(input):
            captured.update(get_propagated_headers())
            return "activity-result"

        mock_next.execute_activity = capture_execute

        interceptor = _ActivityInterceptor(mock_next)

        mock_input = Mock()
        mock_input.headers = {
            "x-identity-token": Payload(data=b"jwt-value"),
            "x-request-id": Payload(data=b"req-123"),
        }

        result = await interceptor.execute_activity(mock_input)

        assert result == "activity-result"
        assert captured == {"x-identity-token": "jwt-value", "x-request-id": "req-123"}

    @pytest.mark.asyncio
    async def test_clears_contextvar_after_activity(self):
        """ContextVar is cleared after activity execution"""
        mock_next = Mock()
        mock_next.execute_activity = AsyncMock(return_value="result")

        interceptor = _ActivityInterceptor(mock_next)

        mock_input = Mock()
        mock_input.headers = {"x-token": Payload(data=b"val")}

        await interceptor.execute_activity(mock_input)

        # After execution, headers should be cleared
        assert _propagated_headers.get() == {}

    @pytest.mark.asyncio
    async def test_clears_contextvar_on_exception(self):
        """ContextVar is cleared even if activity raises"""
        mock_next = Mock()
        mock_next.execute_activity = AsyncMock(side_effect=RuntimeError("boom"))

        interceptor = _ActivityInterceptor(mock_next)

        mock_input = Mock()
        mock_input.headers = {"x-token": Payload(data=b"val")}

        with pytest.raises(RuntimeError, match="boom"):
            await interceptor.execute_activity(mock_input)

        assert _propagated_headers.get() == {}

    @pytest.mark.asyncio
    async def test_handles_empty_headers(self):
        """Works with empty headers dict"""
        mock_next = Mock()
        mock_next.execute_activity = AsyncMock(return_value="result")

        interceptor = _ActivityInterceptor(mock_next)

        mock_input = Mock()
        mock_input.headers = {}

        await interceptor.execute_activity(mock_input)

        assert _propagated_headers.get() == {}

    @pytest.mark.asyncio
    async def test_handles_none_headers(self):
        """Works when headers is None"""
        mock_next = Mock()
        mock_next.execute_activity = AsyncMock(return_value="result")

        interceptor = _ActivityInterceptor(mock_next)

        mock_input = Mock()
        mock_input.headers = None

        await interceptor.execute_activity(mock_input)

        assert _propagated_headers.get() == {}


class TestHeaderPropagationInterceptor:
    def test_intercept_activity_returns_activity_interceptor(self):
        """intercept_activity wraps next with _ActivityInterceptor"""
        interceptor = HeaderPropagationInterceptor()
        mock_next = Mock()

        result = interceptor.intercept_activity(mock_next)

        assert isinstance(result, _ActivityInterceptor)

    def test_workflow_interceptor_class_returns_inbound(self):
        """workflow_interceptor_class returns _WorkflowInbound"""
        interceptor = HeaderPropagationInterceptor()
        mock_input = Mock()

        result = interceptor.workflow_interceptor_class(mock_input)

        assert result is _WorkflowInbound
