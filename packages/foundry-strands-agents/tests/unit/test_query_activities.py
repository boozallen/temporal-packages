# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for Strands Query API activities"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from foundry_strands_agents.exceptions import QueryProcessingError
from foundry_strands_agents.query_activities import (
    _execute_query_call,
    _validate_query_response,
    call_strands_query,
    call_strands_query_dataclass,
)
from foundry_strands_agents.query_models import StrandsQueryTaskInput
from temporalio.exceptions import ApplicationError


class TestExecuteQueryCall:
    """Test suite for _execute_query_call function."""

    @pytest.fixture
    def mock_query_client(self):
        """Create a mock query client."""
        return AsyncMock()

    @pytest.fixture
    def mock_query_response(self):
        """Mock query response data."""
        return {
            "response_text": "The system uses dependency injection patterns.",
            "sources": [],
            "chunks_used": [],
            "confidence_score": 0.85,
            "processing_time_ms": 150.5,
            "timestamp": "2024-01-15T10:30:45.123456Z",
        }

    @pytest.fixture
    def mock_activity_context(self):
        """Mock Temporal activity context."""
        with patch("foundry_strands_agents.query_activities.activity") as mock_activity:
            mock_activity.heartbeat = MagicMock()
            yield mock_activity

    @pytest.mark.asyncio
    async def test_execute_query_call_basic(self, mock_query_client, mock_query_response, mock_activity_context):
        """Test basic query execution."""
        with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_query_client
            mock_query_client.query_agent = AsyncMock(return_value=mock_query_response)

            task_params = {
                "query": "What are the features?",
                "context": {"source": "test"},
                "session_id": "test-session",
                "max_results": 15,
                "similarity_threshold": 0.8,
            }

            result = await _execute_query_call(
                agent_url="http://test-agent:8000",
                task_params=task_params,
                timeout_seconds=300,
                heartbeat_timeout_seconds=None,
                validate_response=False,
                wrapper_func=lambda: None,
            )

            assert result == mock_query_response
            mock_query_client.query_agent.assert_called_once_with(
                query="What are the features?",
                context={"source": "test"},
                session_id="test-session",
                max_results=15,
                similarity_threshold=0.8,
            )

    @pytest.mark.asyncio
    async def test_execute_query_call_invalid_task_params(self):
        """Test query execution with invalid task params."""
        with pytest.raises(ValueError, match="Query activity function must return dict"):
            await _execute_query_call(
                agent_url="http://test-agent:8000",
                task_params="invalid",  # Should be dict
                timeout_seconds=300,
                heartbeat_timeout_seconds=None,
                validate_response=False,
                wrapper_func=lambda: None,
            )

    @pytest.mark.asyncio
    async def test_execute_query_call_uses_max_retries_zero(
        self, mock_query_client, mock_query_response, mock_activity_context
    ):
        """Test that _execute_query_call always constructs the client with max_retries=0.

        Temporal's own activity retry policy is the sole retry authority when this
        is invoked from a Temporal activity.
        """
        with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_query_client
            mock_query_client.query_agent = AsyncMock(return_value=mock_query_response)

            task_params = {"query": "test"}

            await _execute_query_call(
                agent_url="http://test-agent:8000",
                task_params=task_params,
                timeout_seconds=300,
                heartbeat_timeout_seconds=None,
                validate_response=False,
                wrapper_func=lambda: None,
            )

            _, kwargs = mock_client_class.call_args
            assert kwargs["max_retries"] == 0

    @pytest.mark.asyncio
    async def test_execute_query_call_attaches_bearer_token_when_configured(
        self, mock_query_client, mock_query_response, mock_activity_context, monkeypatch, caplog
    ):
        """Test that the deprecated alias still attaches the bearer credential, with a deprecation warning."""
        monkeypatch.delenv("FOUNDRY_AGENT_BEARER_TOKEN", raising=False)
        monkeypatch.setenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", "test-bearer-token")
        with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_query_client
            mock_query_client.query_agent = AsyncMock(return_value=mock_query_response)

            await _execute_query_call(
                agent_url="http://test-agent:8000",
                task_params={"query": "test"},
                timeout_seconds=300,
                heartbeat_timeout_seconds=None,
                validate_response=False,
                wrapper_func=lambda: None,
            )

            _, kwargs = mock_client_class.call_args
            assert kwargs["auth_headers"] == {"Authorization": "Bearer test-bearer-token"}
            assert "FOUNDRY_AGENT_QUERY_BEARER_TOKEN is deprecated" in caplog.text

    @pytest.mark.asyncio
    async def test_execute_query_call_no_bearer_token_sends_empty_auth_headers_and_warns(
        self, mock_query_client, mock_query_response, mock_activity_context, monkeypatch, caplog
    ):
        """Test that a missing bearer credential results in empty auth_headers and a warning, not an error."""
        monkeypatch.delenv("FOUNDRY_AGENT_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", raising=False)
        with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_query_client
            mock_query_client.query_agent = AsyncMock(return_value=mock_query_response)

            await _execute_query_call(
                agent_url="http://test-agent:8000",
                task_params={"query": "test"},
                timeout_seconds=300,
                heartbeat_timeout_seconds=None,
                validate_response=False,
                wrapper_func=lambda: None,
            )

            _, kwargs = mock_client_class.call_args
            assert kwargs["auth_headers"] == {}
            assert "Neither FOUNDRY_AGENT_BEARER_TOKEN nor FOUNDRY_AGENT_QUERY_BEARER_TOKEN" in caplog.text
            assert "deprecated" not in caplog.text

    @pytest.mark.asyncio
    async def test_execute_query_call_forwards_identity_header_alongside_bearer_token(
        self, mock_query_client, mock_query_response, mock_activity_context, monkeypatch
    ):
        """Test that a propagated x-identity-token header is still forwarded, for backward
        compatibility with agent deployments that read it, but is never relied on as the
        authentication signal - the bearer token is."""
        from foundry_temporal.header_propagation import _propagated_headers

        monkeypatch.setenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", "test-bearer-token")
        token = _propagated_headers.set({"x-identity-token": "raw-identity-value"})
        try:
            with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
                mock_client_class.return_value.__aenter__.return_value = mock_query_client
                mock_query_client.query_agent = AsyncMock(return_value=mock_query_response)

                await _execute_query_call(
                    agent_url="http://test-agent:8000",
                    task_params={"query": "test"},
                    timeout_seconds=300,
                    heartbeat_timeout_seconds=None,
                    validate_response=False,
                    wrapper_func=lambda: None,
                )

                _, kwargs = mock_client_class.call_args
                assert kwargs["auth_headers"] == {
                    "Authorization": "Bearer test-bearer-token",
                    "x-identity-token": "raw-identity-value",
                }
        finally:
            _propagated_headers.reset(token)

    @pytest.mark.asyncio
    async def test_execute_query_call_no_propagated_identity_header_sends_only_bearer(
        self, mock_query_client, mock_query_response, mock_activity_context, monkeypatch
    ):
        """Test that auth_headers contains only the bearer token when no identity header
        was propagated."""
        from foundry_temporal.header_propagation import _propagated_headers

        monkeypatch.setenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", "test-bearer-token")
        token = _propagated_headers.set(None)
        try:
            with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
                mock_client_class.return_value.__aenter__.return_value = mock_query_client
                mock_query_client.query_agent = AsyncMock(return_value=mock_query_response)

                await _execute_query_call(
                    agent_url="http://test-agent:8000",
                    task_params={"query": "test"},
                    timeout_seconds=300,
                    heartbeat_timeout_seconds=None,
                    validate_response=False,
                    wrapper_func=lambda: None,
                )

                _, kwargs = mock_client_class.call_args
                assert kwargs["auth_headers"] == {"Authorization": "Bearer test-bearer-token"}
        finally:
            _propagated_headers.reset(token)

    @pytest.mark.asyncio
    async def test_execute_query_call_non_retryable_error_becomes_application_error(
        self, mock_query_client, mock_activity_context
    ):
        """Test that a non-retryable QueryProcessingError surfaces as a non-retryable
        Temporal ApplicationError, so Temporal's retry policy respects the classification.
        """
        with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_query_client
            mock_query_client.query_agent = AsyncMock(
                side_effect=QueryProcessingError("bad request", {"status": 422}, retryable=False)
            )

            with pytest.raises(ApplicationError) as exc_info:
                await _execute_query_call(
                    agent_url="http://test-agent:8000",
                    task_params={"query": "test"},
                    timeout_seconds=300,
                    heartbeat_timeout_seconds=None,
                    validate_response=False,
                    wrapper_func=lambda: None,
                )

            assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    async def test_execute_query_call_retryable_error_propagates_unchanged(
        self, mock_query_client, mock_activity_context
    ):
        """Test that a retryable QueryProcessingError propagates as-is (not wrapped)."""
        with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_query_client
            mock_query_client.query_agent = AsyncMock(
                side_effect=QueryProcessingError("transient failure", retryable=True)
            )

            with pytest.raises(QueryProcessingError):
                await _execute_query_call(
                    agent_url="http://test-agent:8000",
                    task_params={"query": "test"},
                    timeout_seconds=300,
                    heartbeat_timeout_seconds=None,
                    validate_response=False,
                    wrapper_func=lambda: None,
                )


class TestValidateQueryResponse:
    """Test suite for _validate_query_response function."""

    def test_validate_non_dict_response(self, caplog):
        """Test validation with non-dict response logs warning."""
        _validate_query_response("string response", "http://test-agent:8000")
        assert "returned non-dict response" in caplog.text

    def test_validate_dict_response_success(self, caplog):
        """Test validation with valid dict response."""
        response = {"response_text": "Test response", "confidence_score": 0.8, "processing_time_ms": 100}
        _validate_query_response(response, "http://test-agent:8000")
        # Function should complete without exception


class TestBuiltInActivities:
    """Test suite for built-in query activities."""

    @pytest.mark.asyncio
    async def test_call_strands_query_basic(self):
        """Test call_strands_query function with basic parameters."""
        raw_func = call_strands_query.__wrapped__
        result = await raw_func("What are the features?")
        expected = {
            "query": "What are the features?",
            "context": {},
            "session_id": None,
            "max_results": 10,
            "similarity_threshold": 0.7,
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_call_strands_query_dataclass_basic(self):
        """Test call_strands_query_dataclass function with basic parameters."""
        input_data = StrandsQueryTaskInput(query="What are the features?")
        raw_func = call_strands_query_dataclass.__wrapped__
        result = await raw_func(input_data)
        expected = {
            "query": "What are the features?",
            "context": {},
            "session_id": None,
            "max_results": 10,
            "similarity_threshold": 0.7,
        }
        assert result == expected

    def test_call_strands_query_has_activity_metadata(self):
        """Test that call_strands_query has proper activity metadata."""
        assert callable(call_strands_query)
        assert hasattr(call_strands_query, "__wrapped__")

    @pytest.mark.asyncio
    async def test_call_strands_query_dataclass_accepts_dict_input(self):
        """Test that call_strands_query_dataclass handles dict input from Temporal deserialization."""
        dict_input = {
            "query": "What are the features?",
            "session_id": "sess-1",
            "max_results": 10,
            "similarity_threshold": 0.7,
            "additional_params": {},
        }

        with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.query_agent = AsyncMock(return_value={"response_text": "ok"})
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("foundry_strands_agents.query_activities.activity"):
                result = await call_strands_query_dataclass("http://agent:8000", dict_input)

            assert result == {"response_text": "ok"}
            mock_client.query_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_strands_query_dataclass_accepts_temporal_style_dict_input(self, temporal_style_input):
        """
        Temporal-style input test: activity must accept dict input (as delivered
        by Temporal's default data converter when invoked by string name).
        Without coercion in the wrapper, this fails with AttributeError.
        """
        typed = StrandsQueryTaskInput(
            query="What are the features?",
            context={"source": "test"},
            session_id="sess-1",
            max_results=10,
            similarity_threshold=0.7,
            additional_params={},
        )
        dict_input = temporal_style_input(typed)

        with patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.query_agent = AsyncMock(return_value={"response_text": "ok"})
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("foundry_strands_agents.query_activities.activity"):
                result = await call_strands_query_dataclass("http://agent:8000", dict_input)

            assert result == {"response_text": "ok"}
            mock_client.query_agent.assert_called_once()

    def test_call_strands_query_dataclass_has_activity_metadata(self):
        """Test that call_strands_query_dataclass has proper activity metadata."""
        assert callable(call_strands_query_dataclass)
        assert hasattr(call_strands_query_dataclass, "__wrapped__")


class TestExecuteQueryCallTls:
    @pytest.mark.asyncio
    async def test_tls_context_passed_to_query_client(self, monkeypatch):
        """Verify _execute_query_call passes TLS context from env to StrandsQueryClient"""
        import ssl

        mock_ctx = ssl.create_default_context()
        monkeypatch.delenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", raising=False)

        with (
            patch(
                "foundry_strands_agents.query_activities.create_agent_tls_context",
                return_value=mock_ctx,
            ),
            patch("foundry_strands_agents.query_activities.StrandsQueryClient") as mock_client_cls,
            patch("temporalio.activity.heartbeat"),
        ):
            mock_client = AsyncMock()
            mock_client.query_agent = AsyncMock(return_value={"answer": "test"})
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await _execute_query_call(
                agent_url="https://agent.example.com",
                task_params={"query": "hello"},
                timeout_seconds=30,
                heartbeat_timeout_seconds=None,
                validate_response=False,
                wrapper_func=MagicMock(),
            )

            mock_client_cls.assert_called_once_with(
                agent_url="https://agent.example.com",
                timeout=30,
                max_retries=0,
                auth_headers={},
                ssl_context=mock_ctx,
            )
