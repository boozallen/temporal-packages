# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal_agents.exceptions module"""

from foundry_temporal_agents.exceptions import (
    A2AProtocolError,
    AgentCapabilityError,
    AgentNotFoundError,
    AgentTimeoutError,
    StrandsAgentError,
)


class TestStrandsAgentError:
    def test_base_exception(self):
        """Test base exception class"""
        error = StrandsAgentError("test error")
        assert str(error) == "test error"
        assert isinstance(error, Exception)


class TestAgentNotFoundError:
    def test_basic_error(self):
        """Test AgentNotFoundError with basic parameters"""
        agent_url = "http://example.com/agent"
        error = AgentNotFoundError(agent_url)

        assert error.agent_url == agent_url
        assert error.original_error is None
        assert str(error) == f"Agent not found at {agent_url}"
        assert isinstance(error, StrandsAgentError)

    def test_error_with_original_exception(self):
        """Test AgentNotFoundError with original exception"""
        agent_url = "http://example.com/agent"
        original_error = ConnectionError("Connection failed")
        error = AgentNotFoundError(agent_url, original_error)

        assert error.agent_url == agent_url
        assert error.original_error is original_error
        assert str(error) == f"Agent not found at {agent_url}"

    def test_error_with_404_status(self):
        """Test that a 404 keeps the not-found message"""
        agent_url = "http://example.com/agent"
        error = AgentNotFoundError(agent_url, status=404)

        assert error.status == 404
        assert str(error) == f"Agent not found at {agent_url}"

    def test_error_with_other_status_names_the_status(self):
        """Test that a retried 429 or 5xx is not reported as not found"""
        agent_url = "http://example.com/agent"
        error = AgentNotFoundError(agent_url, status=429)

        assert error.status == 429
        assert str(error) == f"Agent at {agent_url} failed with HTTP 429"


class TestAgentTimeoutError:
    def test_timeout_error(self):
        """Test AgentTimeoutError"""
        agent_url = "http://example.com/agent"
        timeout_seconds = 300
        error = AgentTimeoutError(agent_url, timeout_seconds)

        assert error.agent_url == agent_url
        assert error.timeout_seconds == timeout_seconds
        assert str(error) == f"Agent timeout after {timeout_seconds}s: {agent_url}"
        assert isinstance(error, StrandsAgentError)


class TestA2AProtocolError:
    def test_basic_protocol_error(self):
        """Test A2AProtocolError with message only"""
        message = "Invalid protocol format"
        error = A2AProtocolError(message)

        assert error.response_data is None
        assert str(error) == message
        assert isinstance(error, StrandsAgentError)

    def test_protocol_error_with_response_data(self):
        """Test A2AProtocolError with response data"""
        message = "Invalid protocol format"
        response_data = {"error": "invalid_request"}
        error = A2AProtocolError(message, response_data)

        assert error.response_data == response_data
        assert str(error) == message


class TestAgentCapabilityError:
    def test_basic_capability_error(self):
        """Test AgentCapabilityError with basic parameters"""
        agent_name = "test-agent"
        capability = "file_operations"
        error = AgentCapabilityError(agent_name, capability)

        assert error.agent_name == agent_name
        assert error.capability == capability
        assert error.available_capabilities == []
        expected_msg = f"Agent '{agent_name}' does not support required capability: {capability}"
        assert str(error) == expected_msg
        assert isinstance(error, StrandsAgentError)

    def test_capability_error_with_available_capabilities(self):
        """Test AgentCapabilityError with available capabilities list"""
        agent_name = "test-agent"
        capability = "file_operations"
        available_capabilities = ["text_processing", "web_search"]
        error = AgentCapabilityError(agent_name, capability, available_capabilities)

        assert error.agent_name == agent_name
        assert error.capability == capability
        assert error.available_capabilities == available_capabilities
        expected_msg = f"Agent '{agent_name}' does not support required capability: {capability}"
        assert str(error) == expected_msg

    def test_capability_error_with_none_capabilities(self):
        """Test AgentCapabilityError with None capabilities (should default to empty list)"""
        agent_name = "test-agent"
        capability = "file_operations"
        error = AgentCapabilityError(agent_name, capability, None)

        assert error.available_capabilities == []
