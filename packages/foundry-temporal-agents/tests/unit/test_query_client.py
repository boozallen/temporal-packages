# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for StrandsQueryClient"""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from foundry_temporal_agents.exceptions import (
    AgentNotFoundError,
    AgentTimeoutError,
    AgentUnavailableError,
    QueryProcessingError,
)
from foundry_temporal_agents.query_client import StrandsQueryClient


class TestStrandsQueryClient:
    """Test suite for StrandsQueryClient functionality."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock aiohttp session."""
        session = AsyncMock(spec=aiohttp.ClientSession)
        return session

    @pytest.fixture
    def client_with_session(self, mock_session):
        """Create a query client with mock session."""
        return StrandsQueryClient("http://test-agent:8000", session=mock_session)

    @pytest.fixture
    def mock_response_data(self):
        """Mock successful query response data."""
        return {
            "response_text": "The system uses a modular architecture with dependency injection.",
            "sources": [
                {
                    "document_id": "doc_123",
                    "content_preview": "The architecture follows SOLID principles...",
                    "similarity_score": 0.92,
                    "metadata": {"type": "documentation"},
                }
            ],
            "chunks_used": [
                {
                    "chunk_id": "chunk_001",
                    "content": "Dependency injection pattern allows for flexible...",
                    "source_document_id": "doc_123",
                    "chunk_index": 0,
                    "character_start": 0,
                    "character_end": 150,
                    "metadata": {"section": "architecture"},
                }
            ],
            "confidence_score": 0.89,
            "processing_time_ms": 245.7,
            "timestamp": "2024-01-15T10:30:45.123456Z",
            "correlation_id": "req_abc123",
            "api_version": "1.0",
        }

    def test_init_default_values(self):
        """Test client initialization with default values."""
        client = StrandsQueryClient("http://test-agent:8000")

        assert client.agent_url == "http://test-agent:8000"
        assert client.timeout == 300
        assert client.max_retries == 3
        assert client._session is None
        assert client._owns_session is True
        assert client.auth_headers == {}

    def test_init_with_auth_headers(self):
        """Test client initialization with auth headers."""
        client = StrandsQueryClient("http://test-agent:8000", auth_headers={"x-identity-token": "abc123"})

        assert client.auth_headers == {"x-identity-token": "abc123"}

    def test_init_max_retries_zero(self):
        """Test client initialization with max_retries=0 (Temporal-activity usage)."""
        client = StrandsQueryClient("http://test-agent:8000", max_retries=0)

        assert client.max_retries == 0

    def test_init_with_session(self, mock_session):
        """Test client initialization with provided session."""
        client = StrandsQueryClient("http://test-agent:8000", session=mock_session)

        assert client._session is mock_session
        assert client._owns_session is False

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from agent URL."""
        client = StrandsQueryClient("http://test-agent:8000/")
        assert client.agent_url == "http://test-agent:8000"

    @pytest.mark.asyncio
    async def test_context_manager_creates_session(self):
        """Test context manager creates session when none provided."""
        client = StrandsQueryClient("http://test-agent:8000")

        async with client:
            assert client._session is not None
            assert isinstance(client._session, aiohttp.ClientSession)

    @pytest.mark.asyncio
    async def test_context_manager_closes_owned_session(self):
        """Test context manager closes session if it owns it."""
        client = StrandsQueryClient("http://test-agent:8000")

        async with client:
            session = client._session
            assert session is not None
            session.close = AsyncMock()

        # Verify session.close was called
        session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_preserves_external_session(self, mock_session):
        """Test context manager doesn't close externally provided session."""
        client = StrandsQueryClient("http://test-agent:8000", session=mock_session)

        async with client:
            pass

        # Verify session.close was NOT called
        mock_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_agent_success(self, client_with_session, mock_session, mock_response_data):
        """Test successful query agent call."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        result = await client_with_session.query_agent(
            query="What are the main features?",
            context={"source": "test"},
            session_id="test-session",
            max_results=15,
            similarity_threshold=0.8,
        )

        # Verify request was made correctly
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://test-agent:8000/api/v1/query"

        request_data = call_args.kwargs["json"]
        assert request_data["query"] == "What are the main features?"
        assert request_data["context"] == {"source": "test"}
        assert request_data["session_id"] == "test-session"
        assert request_data["max_results"] == 15
        assert request_data["similarity_threshold"] == 0.8

        # Verify response
        assert result == mock_response_data

    @pytest.mark.asyncio
    async def test_query_agent_sends_auth_headers(self, mock_session, mock_response_data):
        """Test that auth_headers are attached to the outbound request."""
        client = StrandsQueryClient(
            "http://test-agent:8000",
            session=mock_session,
            auth_headers={"x-identity-token": "test-jwt-value"},
        )

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.raise_for_status = MagicMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response

        await client.query_agent("test query")

        call_args = mock_session.post.call_args
        assert call_args.kwargs["headers"] == {"x-identity-token": "test-jwt-value"}

    @pytest.mark.asyncio
    async def test_query_agent_no_auth_headers_sends_empty_dict(
        self, client_with_session, mock_session, mock_response_data
    ):
        """Test that no auth_headers results in an empty headers dict, not None."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.raise_for_status = MagicMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response

        await client_with_session.query_agent("test query")

        call_args = mock_session.post.call_args
        assert call_args.kwargs["headers"] == {}

    @pytest.mark.asyncio
    async def test_query_agent_with_kwargs(self, client_with_session, mock_session, mock_response_data):
        """Test query agent call with additional kwargs."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        _ = await client_with_session.query_agent(query="Test query", priority="high", custom_param="value")

        # Verify additional kwargs were included
        call_args = mock_session.post.call_args
        request_data = call_args.kwargs["json"]
        assert request_data["priority"] == "high"
        assert request_data["custom_param"] == "value"

    @pytest.mark.asyncio
    async def test_query_agent_404_error(self, client_with_session, mock_session):
        """Test query agent call with 404 error."""
        mock_response = AsyncMock()
        mock_response.status = 404

        mock_session.post.return_value.__aenter__.return_value = mock_response

        with patch("asyncio.sleep") as mock_sleep:
            with pytest.raises(AgentNotFoundError) as exc_info:
                await client_with_session.query_agent("test query")

        assert "http://test-agent:8000" in str(exc_info.value)
        assert exc_info.value.status == 404
        # 404 is not retried
        mock_session.post.assert_called_once()
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_agent_non_json_200_has_no_status(self, client_with_session, mock_session):
        """Test that a 200 with a non-JSON body is not reported as an HTTP failure."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(
            side_effect=aiohttp.ContentTypeError(request_info=MagicMock(), history=(), status=200)
        )
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with patch("asyncio.sleep"):
            with pytest.raises(AgentNotFoundError) as exc_info:
                await client_with_session.query_agent("test query")

        assert exc_info.value.status is None
        assert "HTTP 200" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_agent_non_dict_response(self, client_with_session, mock_session):
        """Test query agent call with non-dict response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value="invalid response")
        mock_response.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(QueryProcessingError) as exc_info:
            await client_with_session.query_agent("test query")

        assert "Invalid query response format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_agent_timeout_error(self, client_with_session, mock_session):
        """Test query agent call with timeout error."""
        mock_session.post.side_effect = TimeoutError("Request timeout")

        with pytest.raises(AgentTimeoutError) as exc_info:
            await client_with_session.query_agent("test query")

        assert "http://test-agent:8000" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_agent_connection_error(self, client_with_session, mock_session):
        """Test query agent call with connection error."""
        mock_session.post.side_effect = aiohttp.ClientError("Connection failed")

        with pytest.raises(AgentNotFoundError):
            await client_with_session.query_agent("test query")

    @pytest.mark.asyncio
    async def test_query_agent_retries(self, client_with_session, mock_session, mock_response_data):
        """Test query agent call with retries."""
        # First call fails, second succeeds
        mock_response_fail = AsyncMock()
        mock_response_fail.status = 500
        mock_response_fail.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=500
        )

        mock_response_success = AsyncMock()
        mock_response_success.status = 200
        mock_response_success.json = AsyncMock(return_value=mock_response_data)
        mock_response_success.raise_for_status = MagicMock()

        mock_session.post.return_value.__aenter__.side_effect = [mock_response_fail, mock_response_success]

        result = await client_with_session.query_agent("test query")

        # Verify both calls were made
        assert mock_session.post.call_count == 2
        assert result == mock_response_data

    @pytest.mark.asyncio
    async def test_query_agent_5xx_is_retryable(self, client_with_session, mock_session):
        """Test that a 5xx response is retried up to max_retries, then raises AgentUnavailableError."""
        mock_response = AsyncMock()
        mock_response.status = 503
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=503)
        )
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(AgentUnavailableError):
            await client_with_session.query_agent("test query")

        # default max_retries=3 -> 4 total attempts
        assert mock_session.post.call_count == 4

    @pytest.mark.asyncio
    async def test_query_agent_429_is_retryable_and_keeps_status(self, mock_session):
        """Test that a 429 is treated as retryable and its status is kept on the error."""
        client = StrandsQueryClient("http://test-agent:8000", session=mock_session, max_retries=0)
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=429)
        )
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(AgentNotFoundError) as exc_info:
            await client.query_agent("test query")

        assert exc_info.value.status == 429
        assert "HTTP 429" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_agent_4xx_is_non_retryable(self, client_with_session, mock_session):
        """Test that a 4xx response fails fast without consuming the retry budget."""
        mock_response = AsyncMock()
        mock_response.status = 422
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=422)
        )
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(QueryProcessingError) as exc_info:
            await client_with_session.query_agent("test query")

        assert exc_info.value.retryable is False
        assert exc_info.value.context["status"] == 422
        # No retries — fails on first attempt
        assert mock_session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_query_agent_max_retries_zero_single_attempt(self, mock_session):
        """Test that max_retries=0 makes exactly one attempt (Temporal-activity usage)."""
        client = StrandsQueryClient("http://test-agent:8000", session=mock_session, max_retries=0)

        mock_response = AsyncMock()
        mock_response.status = 503
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=503)
        )
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(AgentNotFoundError):
            await client.query_agent("test query")

        assert mock_session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_health_check_success(self, client_with_session, mock_session):
        """Test successful health check."""
        mock_response = AsyncMock()
        mock_response.status = 200

        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await client_with_session.health_check()

        assert result is True
        mock_session.get.assert_called_once_with(
            "http://test-agent:8000/health", timeout=aiohttp.ClientTimeout(total=10)
        )

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client_with_session, mock_session):
        """Test failed health check."""
        mock_response = AsyncMock()
        mock_response.status = 500

        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await client_with_session.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self, client_with_session, mock_session):
        """Test health check with exception."""
        mock_session.get.side_effect = Exception("Connection error")

        result = await client_with_session.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_close_owned_session(self):
        """Test closing owned session."""
        client = StrandsQueryClient("http://test-agent:8000")
        client._session = AsyncMock()
        client._owns_session = True

        await client.close()
        client._session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_external_session(self, mock_session):
        """Test not closing external session."""
        client = StrandsQueryClient("http://test-agent:8000", session=mock_session)

        await client.close()
        mock_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_agent_stream_sse_parsing(self, client_with_session, mock_session):
        """Test streaming query with SSE event parsing."""
        # Mock streaming response content
        sse_data = [
            b"event: token\n",
            b'data: {"content": "Hello", "correlation_id": "123"}\n',
            b"\n",
            b"event: done\n",
            b'data: {"processing_time_ms": 100, "session_id": "sess123"}\n',
            b"\n",
        ]

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()

        # Create proper async iterator mock
        class MockAsyncIterator:
            def __init__(self, data):
                self.data = iter(data)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.data)
                except StopIteration:
                    raise StopAsyncIteration from None

        mock_response.content = MockAsyncIterator(sse_data)

        mock_session.post.return_value.__aenter__.return_value = mock_response

        events = []
        async for event in client_with_session.query_agent_stream("test query"):
            events.append(event)

        assert len(events) == 2
        assert events[0]["content"] == "Hello"
        assert events[1]["processing_time_ms"] == 100

    @pytest.mark.asyncio
    async def test_query_agent_stream_404_error(self, client_with_session, mock_session):
        """Test streaming query with 404 error."""
        mock_response = AsyncMock()
        mock_response.status = 404

        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(AgentNotFoundError) as exc_info:
            async for _ in client_with_session.query_agent_stream("test query"):
                pass

        assert exc_info.value.status == 404

    @pytest.mark.asyncio
    async def test_query_agent_stream_timeout_error(self, client_with_session, mock_session):
        """Test streaming query with timeout error."""
        mock_session.post.side_effect = TimeoutError("Request timeout")

        with pytest.raises(AgentTimeoutError):
            async for _ in client_with_session.query_agent_stream("test query"):
                pass

    @pytest.mark.asyncio
    async def test_query_agent_stream_connection_error(self, client_with_session, mock_session):
        """Test streaming query with connection error."""
        mock_session.post.side_effect = aiohttp.ClientError("Connection failed")

        with pytest.raises(AgentNotFoundError):
            async for _ in client_with_session.query_agent_stream("test query"):
                pass

    @pytest.mark.asyncio
    async def test_query_agent_stream_5xx_is_retryable_shaped_error(self, client_with_session, mock_session):
        """Test that a 5xx response streaming raises AgentUnavailableError (retryable), not QueryProcessingError."""
        mock_response = AsyncMock()
        mock_response.status = 503
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=503)
        )
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(AgentUnavailableError):
            async for _ in client_with_session.query_agent_stream("test query"):
                pass

    @pytest.mark.asyncio
    async def test_query_agent_stream_429_is_retryable_and_keeps_status(self, client_with_session, mock_session):
        """Test that a 429 while streaming raises a retryable AgentNotFoundError that names the status."""
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=429)
        )
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(AgentNotFoundError) as exc_info:
            async for _ in client_with_session.query_agent_stream("test query"):
                pass

        assert exc_info.value.status == 429
        assert "HTTP 429" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_agent_stream_4xx_is_non_retryable(self, client_with_session, mock_session):
        """Test that a 4xx response streaming raises QueryProcessingError(retryable=False)."""
        mock_response = AsyncMock()
        mock_response.status = 422
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=422)
        )
        mock_session.post.return_value.__aenter__.return_value = mock_response

        with pytest.raises(QueryProcessingError) as exc_info:
            async for _ in client_with_session.query_agent_stream("test query"):
                pass

        assert exc_info.value.retryable is False
        assert exc_info.value.context["status"] == 422

    @pytest.mark.asyncio
    async def test_ensure_session_creates_when_none(self):
        """Test _ensure_session creates session when none exists."""
        client = StrandsQueryClient("http://test-agent:8000")
        assert client._session is None

        await client._ensure_session()
        assert client._session is not None
        assert isinstance(client._session, aiohttp.ClientSession)

        # Clean up
        await client.close()

    @pytest.mark.asyncio
    async def test_ensure_session_preserves_existing(self, mock_session):
        """Test _ensure_session preserves existing session."""
        client = StrandsQueryClient("http://test-agent:8000", session=mock_session)

        await client._ensure_session()
        assert client._session is mock_session

    @pytest.mark.asyncio
    async def test_ssl_context_passed_to_connector(self):
        """Test that ssl_context is used when creating a session"""
        import ssl
        from unittest.mock import patch

        ctx = ssl.create_default_context()
        client = StrandsQueryClient("https://secure-agent:8000", ssl_context=ctx)

        with patch("aiohttp.TCPConnector") as mock_connector_cls:
            mock_connector = MagicMock()
            mock_connector_cls.return_value = mock_connector
            with patch("aiohttp.ClientSession") as mock_session_cls:
                mock_session = AsyncMock()
                mock_session_cls.return_value = mock_session

                async with client:
                    pass

                mock_connector_cls.assert_called_once_with(ssl=ctx)
                mock_session_cls.assert_called_once_with(connector=mock_connector)

    @pytest.mark.asyncio
    async def test_no_ssl_context_creates_plain_session(self):
        """Test that no ssl_context creates a plain session"""
        from unittest.mock import patch

        client = StrandsQueryClient("http://test-agent:8000")

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value = mock_session

            async with client:
                pass

            mock_session_cls.assert_called_once_with()
