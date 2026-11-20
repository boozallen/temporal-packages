# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""End-to-end tests for header injection -> propagation -> get_header() flow.

Tests the full lifecycle: client injects headers into workflow start,
workflow outbound copies them to activity, activity interceptor decodes
and exposes via get_header()/get_propagated_headers().
"""

from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.fernet import Fernet
from foundry_temporal.header_injection import (
    HeaderInjectionInterceptor,
    outbound_headers,
)
from foundry_temporal.header_propagation import (
    HeaderPropagationInterceptor,
    _ActivityInterceptor,
    _WorkflowInbound,
    _WorkflowOutbound,
    get_header,
    get_propagated_headers,
)
from temporalio.api.common.v1 import Payload


class TestInjectionToPropagationFlow:
    """Tests the full header lifecycle without encryption."""

    @pytest.mark.asyncio
    async def test_injected_headers_readable_in_activity(self):
        """Headers injected by client are readable via get_header() in activity."""
        # Step 1: Client-side injection (simulates API setting headers)
        interceptor = HeaderInjectionInterceptor()
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")
        outbound = interceptor.intercept_client(mock_next)

        token = outbound_headers.set({"x-identity-token": "user-jwt-123"})

        mock_input = Mock()
        mock_input.headers = {}
        await outbound.start_workflow(mock_input)
        outbound_headers.reset(token)

        # Step 2: Workflow inbound captures headers (simulates workflow start)
        mock_wf_next = Mock()
        mock_wf_next.execute_workflow = AsyncMock(return_value="wf-result")
        mock_wf_next.init = Mock()

        wf_inbound = _WorkflowInbound(mock_wf_next)
        wf_execute_input = Mock()
        wf_execute_input.headers = mock_input.headers  # same headers from step 1
        await wf_inbound.execute_workflow(wf_execute_input)

        # Step 3: Workflow outbound copies to activity (simulates scheduling activity)
        mock_activity_next = Mock()
        mock_activity_next.start_activity = Mock(return_value="activity-handle")
        wf_outbound = _WorkflowOutbound(mock_activity_next, wf_inbound)

        activity_input = Mock()
        activity_input.headers = {}
        wf_outbound.start_activity(activity_input)

        # Step 4: Activity interceptor decodes (simulates activity execution)
        captured_headers = {}

        async def capture_activity(inp):
            captured_headers["token"] = get_header("x-identity-token")
            captured_headers["all"] = get_propagated_headers()
            return "activity-result"

        mock_act_next = Mock()
        mock_act_next.execute_activity = capture_activity

        act_interceptor = _ActivityInterceptor(mock_act_next)
        act_execute_input = Mock()
        act_execute_input.headers = activity_input.headers

        result = await act_interceptor.execute_activity(act_execute_input)

        assert result == "activity-result"
        assert captured_headers["token"] == "user-jwt-123"
        assert captured_headers["all"] == {"x-identity-token": "user-jwt-123"}

    @pytest.mark.asyncio
    async def test_multiple_headers_flow(self):
        """Multiple headers survive the full injection -> propagation flow."""
        interceptor = HeaderInjectionInterceptor()
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")
        outbound = interceptor.intercept_client(mock_next)

        token = outbound_headers.set(
            {
                "x-identity-token": "jwt-abc",
                "x-request-id": "req-456",
                "x-tenant-id": "tenant-789",
            }
        )

        mock_input = Mock()
        mock_input.headers = {}
        await outbound.start_workflow(mock_input)
        outbound_headers.reset(token)

        # Simulate workflow capturing and passing to activity
        mock_wf_next = Mock()
        mock_wf_next.execute_workflow = AsyncMock(return_value="result")
        mock_wf_next.init = Mock()
        wf_inbound = _WorkflowInbound(mock_wf_next)

        wf_input = Mock()
        wf_input.headers = mock_input.headers
        await wf_inbound.execute_workflow(wf_input)

        mock_act_start = Mock()
        mock_act_start.start_activity = Mock(return_value="handle")
        wf_outbound = _WorkflowOutbound(mock_act_start, wf_inbound)

        act_input = Mock()
        act_input.headers = {}
        wf_outbound.start_activity(act_input)

        # Activity reads headers
        captured = {}

        async def capture(inp):
            captured.update(get_propagated_headers())
            return "done"

        mock_act_next = Mock()
        mock_act_next.execute_activity = capture
        act_interceptor = _ActivityInterceptor(mock_act_next)

        exec_input = Mock()
        exec_input.headers = act_input.headers
        await act_interceptor.execute_activity(exec_input)

        assert captured == {
            "x-identity-token": "jwt-abc",
            "x-request-id": "req-456",
            "x-tenant-id": "tenant-789",
        }

    @pytest.mark.asyncio
    async def test_headers_cleared_after_activity(self):
        """get_header() returns None after activity completes."""
        mock_act_next = Mock()
        mock_act_next.execute_activity = AsyncMock(return_value="done")

        act_interceptor = _ActivityInterceptor(mock_act_next)
        exec_input = Mock()
        exec_input.headers = {"x-token": Payload(data=b"secret")}

        await act_interceptor.execute_activity(exec_input)

        # After activity finishes, headers are cleared
        assert get_header("x-token") is None
        assert get_propagated_headers() == {}

    @pytest.mark.asyncio
    async def test_no_headers_injected_no_headers_in_activity(self):
        """When no headers are set, activity sees empty headers."""
        interceptor = HeaderInjectionInterceptor()
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")
        outbound = interceptor.intercept_client(mock_next)

        # Don't set outbound_headers - should be None
        mock_input = Mock()
        mock_input.headers = {}
        await outbound.start_workflow(mock_input)

        # Activity gets empty headers
        captured = {}

        async def capture(inp):
            captured["all"] = get_propagated_headers()
            return "done"

        mock_act_next = Mock()
        mock_act_next.execute_activity = capture
        act_interceptor = _ActivityInterceptor(mock_act_next)

        exec_input = Mock()
        exec_input.headers = mock_input.headers
        await act_interceptor.execute_activity(exec_input)

        assert captured["all"] == {}

    @pytest.mark.asyncio
    async def test_local_activity_receives_headers(self):
        """Headers are also propagated to local activities."""
        mock_wf_next = Mock()
        mock_wf_next.execute_workflow = AsyncMock(return_value="result")
        mock_wf_next.init = Mock()
        wf_inbound = _WorkflowInbound(mock_wf_next)

        wf_input = Mock()
        wf_input.headers = {"x-token": Payload(data=b"jwt")}
        await wf_inbound.execute_workflow(wf_input)

        mock_local_next = Mock()
        mock_local_next.start_local_activity = Mock(return_value="local-handle")
        wf_outbound = _WorkflowOutbound(mock_local_next, wf_inbound)

        local_input = Mock()
        local_input.headers = {}
        wf_outbound.start_local_activity(local_input)

        assert "x-token" in local_input.headers
        assert local_input.headers["x-token"].data == b"jwt"


class TestEncryptedHeaderFlow:
    """Tests the full header lifecycle with Fernet encryption enabled."""

    # Generated per test session rather than hardcoded: a literal Fernet key
    # trips secret scanners on entropy, and these tests only need *a* valid key.
    ENCRYPTION_KEY = Fernet.generate_key().decode()

    @pytest.mark.asyncio
    async def test_encrypted_header_not_plaintext_in_payload(self):
        """Encrypted header value is NOT stored as plaintext in the Payload."""
        interceptor = HeaderInjectionInterceptor(encryption_key=self.ENCRYPTION_KEY)
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")
        outbound = interceptor.intercept_client(mock_next)

        token = outbound_headers.set({"x-identity-token": "my-secret-jwt"})
        mock_input = Mock()
        mock_input.headers = {}
        await outbound.start_workflow(mock_input)
        outbound_headers.reset(token)

        # The payload data should NOT be the plaintext value
        payload_data = mock_input.headers["x-identity-token"].data
        assert payload_data != b"my-secret-jwt"
        # It should be a Fernet token (starts with gAAAAA in base64)
        assert len(payload_data) > len(b"my-secret-jwt")

    @pytest.mark.asyncio
    async def test_encrypted_injection_decrypted_in_activity(self):
        """Full flow: encrypted injection -> workflow propagation -> decrypted in activity."""
        # Step 1: Inject with encryption
        injection = HeaderInjectionInterceptor(encryption_key=self.ENCRYPTION_KEY)
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")
        outbound = injection.intercept_client(mock_next)

        token = outbound_headers.set({"x-identity-token": "secret-jwt-value"})
        mock_input = Mock()
        mock_input.headers = {}
        await outbound.start_workflow(mock_input)
        outbound_headers.reset(token)

        # Step 2: Workflow captures and copies to activity
        mock_wf_next = Mock()
        mock_wf_next.execute_workflow = AsyncMock(return_value="result")
        mock_wf_next.init = Mock()
        wf_inbound = _WorkflowInbound(mock_wf_next)

        wf_input = Mock()
        wf_input.headers = mock_input.headers
        await wf_inbound.execute_workflow(wf_input)

        mock_act_start = Mock()
        mock_act_start.start_activity = Mock(return_value="handle")
        wf_outbound = _WorkflowOutbound(mock_act_start, wf_inbound)

        act_input = Mock()
        act_input.headers = {}
        wf_outbound.start_activity(act_input)

        # Step 3: Activity decrypts with same key
        captured = {}

        async def capture(inp):
            captured["token"] = get_header("x-identity-token")
            captured["all"] = get_propagated_headers()
            return "done"

        mock_act_next = Mock()
        mock_act_next.execute_activity = capture

        propagation = HeaderPropagationInterceptor(encryption_key=self.ENCRYPTION_KEY)
        act_interceptor = propagation.intercept_activity(mock_act_next)

        exec_input = Mock()
        exec_input.headers = act_input.headers
        await act_interceptor.execute_activity(exec_input)

        assert captured["token"] == "secret-jwt-value"
        assert captured["all"] == {"x-identity-token": "secret-jwt-value"}

    @pytest.mark.asyncio
    async def test_multiple_encrypted_headers(self):
        """Multiple headers are all encrypted and decryptable."""
        injection = HeaderInjectionInterceptor(encryption_key=self.ENCRYPTION_KEY)
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")
        outbound = injection.intercept_client(mock_next)

        token = outbound_headers.set(
            {
                "x-identity-token": "jwt-123",
                "x-request-id": "req-abc",
            }
        )
        mock_input = Mock()
        mock_input.headers = {}
        await outbound.start_workflow(mock_input)
        outbound_headers.reset(token)

        # Both should be encrypted (not plaintext)
        assert mock_input.headers["x-identity-token"].data != b"jwt-123"
        assert mock_input.headers["x-request-id"].data != b"req-abc"

        # Decrypt in activity
        captured = {}

        async def capture(inp):
            captured.update(get_propagated_headers())
            return "done"

        mock_act_next = Mock()
        mock_act_next.execute_activity = capture
        propagation = HeaderPropagationInterceptor(encryption_key=self.ENCRYPTION_KEY)
        act_interceptor = propagation.intercept_activity(mock_act_next)

        exec_input = Mock()
        exec_input.headers = mock_input.headers
        await act_interceptor.execute_activity(exec_input)

        assert captured == {"x-identity-token": "jwt-123", "x-request-id": "req-abc"}

    @pytest.mark.asyncio
    async def test_wrong_key_fails_decryption(self):
        """Decryption with a different key raises an error."""
        from cryptography.fernet import InvalidToken

        # Encrypt with one key
        injection = HeaderInjectionInterceptor(encryption_key=self.ENCRYPTION_KEY)
        mock_next = Mock()
        mock_next.start_workflow = AsyncMock(return_value="handle")
        outbound = injection.intercept_client(mock_next)

        token = outbound_headers.set({"x-token": "secret"})
        mock_input = Mock()
        mock_input.headers = {}
        await outbound.start_workflow(mock_input)
        outbound_headers.reset(token)

        # Decrypt with different key. A freshly generated key is guaranteed
        # distinct from ENCRYPTION_KEY for practical purposes.
        wrong_key = Fernet.generate_key().decode()
        propagation = HeaderPropagationInterceptor(encryption_key=wrong_key)
        act_interceptor = propagation.intercept_activity(Mock())

        exec_input = Mock()
        exec_input.headers = mock_input.headers

        with pytest.raises(InvalidToken):
            await act_interceptor.execute_activity(exec_input)

    def test_no_key_no_encryption(self):
        """Without encryption_key, interceptor has no fernet."""
        injection = HeaderInjectionInterceptor()
        assert injection._fernet is None

        propagation = HeaderPropagationInterceptor()
        assert propagation._fernet is None
