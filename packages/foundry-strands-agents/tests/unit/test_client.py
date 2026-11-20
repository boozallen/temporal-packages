# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_strands_agents.client module"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest
from foundry_strands_agents.client import StrandsAgentClient
from foundry_strands_agents.exceptions import A2AProtocolError, AgentNotFoundError, AgentTimeoutError


class TestStrandsAgentClient:
    @pytest.fixture
    def client(self):
        """Create a test client"""
        return StrandsAgentClient("http://test-agent.com", timeout=30, max_retries=2)

    @pytest.fixture
    def mock_session(self):
        """Create a mock aiohttp session"""
        return AsyncMock(spec=aiohttp.ClientSession)

    def test_init_basic(self):
        """Test basic client initialization"""
        client = StrandsAgentClient("http://test-agent.com")

        assert client.agent_url == "http://test-agent.com"
        assert client.timeout == 300  # default
        assert client.max_retries == 3  # default
        assert client._session is None
        assert client._owns_session is True

    def test_init_with_parameters(self):
        """Test client initialization with custom parameters"""
        session = MagicMock()
        client = StrandsAgentClient("http://test-agent.com/", timeout=60, max_retries=5, session=session)

        assert client.agent_url == "http://test-agent.com"  # trailing slash stripped
        assert client.timeout == 60
        assert client.max_retries == 5
        assert client._session is session
        assert client._owns_session is False

    def test_init_with_provided_session(self):
        """Test initialization with provided session"""
        session = MagicMock()
        client = StrandsAgentClient("http://test-agent.com", session=session)

        assert client._session is session
        assert client._owns_session is False

    @pytest.mark.asyncio
    async def test_context_manager_creates_session(self):
        """Test context manager creates session when none provided"""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            client = StrandsAgentClient("http://test-agent.com")

            async with client:
                assert client._session is mock_session
                mock_session_class.assert_called_once()

            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_with_existing_session(self):
        """Test context manager with existing session"""
        existing_session = AsyncMock()
        client = StrandsAgentClient("http://test-agent.com", session=existing_session)

        async with client:
            assert client._session is existing_session

        # Should not close session we don't own
        existing_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_session_creates_session(self):
        """Test _ensure_session creates session if needed"""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session

            client = StrandsAgentClient("http://test-agent.com")
            await client._ensure_session()

            assert client._session is mock_session
            mock_session_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_session_keeps_existing_session(self):
        """Test _ensure_session doesn't replace existing session"""
        existing_session = AsyncMock()
        client = StrandsAgentClient("http://test-agent.com")
        client._session = existing_session

        await client._ensure_session()

        assert client._session is existing_session

    @pytest.mark.asyncio
    async def test_call_agent_success(self, client, mock_session):
        """Test successful agent call"""
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"jsonrpc": "2.0", "result": {"status": "completed", "data": "test response"}, "id": 1}
        )
        mock_response.raise_for_status = AsyncMock()
        mock_response.__aenter__.return_value = mock_response
        mock_session.post.return_value = mock_response

        client._session = mock_session

        # Call agent
        result = await client.call_agent("test task")

        # Verify result
        assert result == {"status": "completed", "data": "test response"}

        # Verify request was made correctly
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://test-agent.com"

        # Verify request structure
        request_data = call_args[1]["json"]
        assert request_data["jsonrpc"] == "2.0"
        assert request_data["method"] == "message/send"
        # The message includes parameters when session_id=None is passed
        expected_text = 'test task\n\nParameters: {"session_id": null}'
        assert request_data["params"]["message"]["parts"][0]["text"] == expected_text

    @pytest.mark.asyncio
    async def test_call_agent_with_extra_data(self, client, mock_session):
        """Test agent call with extra data"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"jsonrpc": "2.0", "result": "success", "id": 1}
        mock_response.__aenter__.return_value = mock_response
        mock_session.post.return_value = mock_response

        client._session = mock_session

        extra_data = {"file": "test.txt"}
        await client.call_agent("test task", extra_data)

        # Verify extra data is in message
        call_args = mock_session.post.call_args
        request_data = call_args[1]["json"]
        message_text = request_data["params"]["message"]["parts"][0]["text"]
        assert "test task" in message_text
        assert json.dumps(extra_data) in message_text

    @pytest.mark.asyncio
    async def test_call_agent_with_session_id(self, client, mock_session):
        """Test agent call with session ID"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"jsonrpc": "2.0", "result": "success", "id": 1}
        mock_response.__aenter__.return_value = mock_response
        mock_session.post.return_value = mock_response

        client._session = mock_session

        await client.call_agent("test task", session_id="session-123")

        # Verify session ID is included
        call_args = mock_session.post.call_args
        request_data = call_args[1]["json"]
        assert request_data["params"]["sessionId"] == "session-123"

    @pytest.mark.asyncio
    async def test_call_agent_404_error(self, client, mock_session):
        """Test agent call with 404 response"""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.__aenter__.return_value = mock_response
        mock_session.post.return_value = mock_response

        client._session = mock_session

        with pytest.raises(AgentNotFoundError) as exc_info:
            await client.call_agent("test task")

        assert exc_info.value.agent_url == client.agent_url
        assert exc_info.value.original_error is None

    @pytest.mark.asyncio
    async def test_call_agent_http_error(self, client, mock_session):
        """Test agent call with HTTP error"""
        # Mock the post request to directly raise ClientError
        error = aiohttp.ClientError("Connection failed")
        mock_session.post.side_effect = error
        client._session = mock_session

        with pytest.raises(AgentNotFoundError):
            await client.call_agent("test task")

    @pytest.mark.asyncio
    async def test_call_agent_timeout(self, client, mock_session):
        """Test agent call timeout"""
        mock_session.post.side_effect = TimeoutError()
        client._session = mock_session

        with pytest.raises(AgentTimeoutError) as exc_info:
            await client.call_agent("test task")

        assert exc_info.value.timeout_seconds == 30

    @pytest.mark.asyncio
    async def test_call_agent_invalid_a2a_response(self, client, mock_session):
        """Test agent call with invalid A2A response"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"invalid": "response"})
        mock_response.raise_for_status = AsyncMock()
        mock_response.__aenter__.return_value = mock_response
        mock_session.post.return_value = mock_response

        client._session = mock_session

        with pytest.raises(A2AProtocolError) as exc_info:
            await client.call_agent("test task")

        assert "Invalid A2A response format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_agent_retry_success(self, client, mock_session):
        """Test agent call succeeds on retry"""
        # First call fails, second succeeds
        error = aiohttp.ClientResponseError(
            request_info=Mock(), history=(), status=500, message="Internal Server Error"
        )
        error_response = AsyncMock()
        error_response.status = 500
        error_response.raise_for_status = AsyncMock(side_effect=error)
        error_response.__aenter__.return_value = error_response

        success_response = AsyncMock()
        success_response.status = 200
        success_response.json = AsyncMock(return_value={"jsonrpc": "2.0", "result": "success", "id": 1})
        success_response.raise_for_status = AsyncMock()
        success_response.__aenter__.return_value = success_response

        mock_session.post.side_effect = [error_response, success_response]
        client._session = mock_session

        with patch("asyncio.sleep"):  # Mock sleep to speed up test
            result = await client.call_agent("test task")

        assert result == "success"
        assert mock_session.post.call_count == 2

    @pytest.mark.asyncio
    async def test_call_agent_retry_exhausted(self, client, mock_session):
        """Test agent call fails after all retries exhausted"""
        mock_session.post.side_effect = aiohttp.ClientError()
        client._session = mock_session

        with patch("asyncio.sleep"):  # Mock sleep to speed up test
            with pytest.raises(AgentNotFoundError):
                await client.call_agent("test task")

        # Should try max_retries + 1 times (2 + 1 = 3)
        assert mock_session.post.call_count == 3

    @pytest.mark.asyncio
    async def test_discover_capabilities_success(self, client, mock_session):
        """Test successful capability discovery"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"name": "test-agent", "version": "1.0.0", "capabilities": ["text_processing", "web_search"]}
        )
        mock_response.raise_for_status = AsyncMock()
        mock_response.__aenter__.return_value = mock_response
        mock_session.get.return_value = mock_response

        client._session = mock_session

        capabilities = await client.discover_capabilities()

        assert capabilities["name"] == "test-agent"
        assert capabilities["capabilities"] == ["text_processing", "web_search"]

        # Verify correct URL was called
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args
        assert call_args[0][0] == "http://test-agent.com/.well-known/agent-card.json"

    @pytest.mark.asyncio
    async def test_discover_capabilities_failure(self, client, mock_session):
        """Test capability discovery failure"""
        mock_session.get.side_effect = aiohttp.ClientError("Not found")
        client._session = mock_session

        with pytest.raises(AgentNotFoundError):
            await client.discover_capabilities()

    @pytest.mark.asyncio
    async def test_health_check_success(self, client, mock_session):
        """Test successful health check"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__.return_value = mock_response
        mock_session.get.return_value = mock_response

        client._session = mock_session

        is_healthy = await client.health_check()

        assert is_healthy is True
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args
        assert call_args[0][0] == "http://test-agent.com/health"

    @pytest.mark.asyncio
    async def test_health_check_2xx_status_codes(self, client, mock_session):
        """Test health check accepts all 2xx status codes"""
        for status in [200, 201, 204, 299]:
            mock_response = AsyncMock()
            mock_response.status = status
            mock_response.__aenter__.return_value = mock_response
            mock_session.get.return_value = mock_response
            mock_session.reset_mock()

            client._session = mock_session

            is_healthy = await client.health_check()
            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure_status_codes(self, client, mock_session):
        """Test health check fails for non-2xx status codes"""
        for status in [400, 404, 500]:
            mock_response = AsyncMock()
            mock_response.status = status
            mock_response.__aenter__.return_value = mock_response
            mock_session.get.return_value = mock_response
            mock_session.reset_mock()

            client._session = mock_session

            is_healthy = await client.health_check()
            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self, client, mock_session):
        """Test health check handles exceptions"""
        mock_session.get.side_effect = aiohttp.ClientError("Connection failed")
        client._session = mock_session

        is_healthy = await client.health_check()

        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_close_owns_session(self):
        """Test close() when client owns the session"""
        mock_session = AsyncMock()
        client = StrandsAgentClient("http://test-agent.com")
        client._session = mock_session
        client._owns_session = True

        await client.close()

        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_doesnt_own_session(self):
        """Test close() when client doesn't own the session"""
        mock_session = AsyncMock()
        client = StrandsAgentClient("http://test-agent.com", session=mock_session)

        await client.close()

        mock_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_no_session(self):
        """Test close() when no session exists"""
        client = StrandsAgentClient("http://test-agent.com")

        # Should not raise exception
        await client.close()

    @pytest.mark.asyncio
    async def test_ssl_context_passed_to_connector(self):
        """Test that ssl_context is used when creating a session"""
        import ssl

        ctx = ssl.create_default_context()
        client = StrandsAgentClient("https://secure-agent.com", ssl_context=ctx)

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
        client = StrandsAgentClient("http://test-agent.com")

        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value = mock_session

            async with client:
                pass

            mock_session_cls.assert_called_once_with()
