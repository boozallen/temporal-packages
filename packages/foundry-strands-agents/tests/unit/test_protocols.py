# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_strands_agents.protocols module"""

import json

import pytest
from foundry_strands_agents.protocols import A2AMessageBuilder, extract_agent_response, validate_a2a_response


class TestA2AMessageBuilder:
    def test_create_request_basic(self):
        """Test basic request creation"""
        builder = A2AMessageBuilder()
        message = "Hello, agent!"
        request = builder.create_request(message)

        assert request["jsonrpc"] == "2.0"
        assert request["method"] == "message/send"
        assert request["id"] == 1
        assert request["params"]["message"]["role"] == "user"
        assert request["params"]["message"]["parts"][0]["kind"] == "text"
        assert request["params"]["message"]["parts"][0]["text"] == message
        assert "messageId" in request["params"]["message"]
        assert "sessionId" not in request["params"]

    def test_create_request_with_session_id(self):
        """Test request creation with session ID"""
        builder = A2AMessageBuilder()
        message = "Hello, agent!"
        session_id = "session-123"
        request = builder.create_request(message, session_id=session_id)

        assert request["params"]["sessionId"] == session_id

    def test_create_request_with_custom_method(self):
        """Test request creation with custom method"""
        builder = A2AMessageBuilder()
        message = "Hello, agent!"
        method = "custom/method"
        request = builder.create_request(message, method=method)

        assert request["method"] == method

    def test_request_id_increments(self):
        """Test that request IDs increment"""
        builder = A2AMessageBuilder()

        request1 = builder.create_request("message 1")
        request2 = builder.create_request("message 2")

        assert request1["id"] == 1
        assert request2["id"] == 2

    def test_message_id_format(self):
        """Test message ID format"""
        builder = A2AMessageBuilder()
        request = builder.create_request("test")

        message_id = request["params"]["message"]["messageId"]
        assert message_id.startswith("foundry-")
        assert len(message_id.split("-")) == 3  # foundry-timestamp-uuid

    def test_create_task_message_basic(self):
        """Test basic task message creation"""
        builder = A2AMessageBuilder()
        task = "Process this document"
        message = builder.create_task_message(task)

        assert message == task

    def test_create_task_message_with_extra_data(self):
        """Test task message with extra data"""
        builder = A2AMessageBuilder()
        task = "Process this document"
        extra_data = {"file_path": "/tmp/doc.txt", "format": "pdf"}

        message = builder.create_task_message(task, extra_data)

        assert task in message
        assert "Extra Data:" in message
        assert json.dumps(extra_data) in message

    def test_create_task_message_with_kwargs(self):
        """Test task message with kwargs"""
        builder = A2AMessageBuilder()
        task = "Process this document"

        message = builder.create_task_message(task, priority="high", deadline="2024-01-01")

        assert task in message
        assert "Parameters:" in message
        assert "priority" in message
        assert "deadline" in message

    def test_create_task_message_with_extra_data_and_kwargs(self):
        """Test task message with both extra data and kwargs"""
        builder = A2AMessageBuilder()
        task = "Process this document"
        extra_data = {"file_path": "/tmp/doc.txt"}

        message = builder.create_task_message(task, extra_data, priority="high")

        assert task in message
        assert "Extra Data:" in message
        assert "Parameters:" in message
        assert json.dumps(extra_data) in message
        assert "priority" in message

    def test_create_task_message_empty_extra_data(self):
        """Test task message with empty extra data"""
        builder = A2AMessageBuilder()
        task = "Process this document"

        message = builder.create_task_message(task, {})

        assert message == task  # No extra content should be added

    def test_create_task_message_none_extra_data(self):
        """Test task message with None extra data"""
        builder = A2AMessageBuilder()
        task = "Process this document"

        message = builder.create_task_message(task, None)

        assert message == task


class TestValidateA2AResponse:
    def test_valid_response_with_result(self):
        """Test valid A2A response with result"""
        response = {"jsonrpc": "2.0", "result": {"status": "completed", "data": "response"}, "id": 1}

        assert validate_a2a_response(response) is True

    def test_valid_response_with_error(self):
        """Test valid A2A response with error"""
        response = {"jsonrpc": "2.0", "error": {"code": -1, "message": "Task failed"}, "id": 1}

        assert validate_a2a_response(response) is True

    def test_invalid_response_not_dict(self):
        """Test invalid response - not a dictionary"""
        assert validate_a2a_response("invalid") is False
        assert validate_a2a_response(None) is False
        assert validate_a2a_response([]) is False

    def test_invalid_response_missing_jsonrpc(self):
        """Test invalid response - missing jsonrpc field"""
        response = {"result": {"status": "completed"}, "id": 1}

        assert validate_a2a_response(response) is False

    def test_invalid_response_wrong_jsonrpc_version(self):
        """Test invalid response - wrong jsonrpc version"""
        response = {"jsonrpc": "1.0", "result": {"status": "completed"}, "id": 1}

        assert validate_a2a_response(response) is False

    def test_invalid_response_no_result_or_error(self):
        """Test invalid response - missing both result and error"""
        response = {"jsonrpc": "2.0", "id": 1}

        assert validate_a2a_response(response) is False

    def test_valid_response_with_both_result_and_error(self):
        """Test response with both result and error (should be valid)"""
        response = {
            "jsonrpc": "2.0",
            "result": {"status": "completed"},
            "error": {"code": -1, "message": "Warning"},
            "id": 1,
        }

        assert validate_a2a_response(response) is True


class TestExtractAgentResponse:
    def test_extract_result(self):
        """Test extracting result from response"""
        response_data = {"result": {"status": "completed", "data": "test"}}
        result = extract_agent_response(response_data)

        assert result == {"status": "completed", "data": "test"}

    def test_extract_result_simple_string(self):
        """Test extracting simple string result"""
        response_data = {"result": "Simple response"}
        result = extract_agent_response(response_data)

        assert result == "Simple response"

    def test_extract_error_raises_exception(self):
        """Test extracting error raises exception"""
        response_data = {"error": {"code": -1, "message": "Task failed"}}

        with pytest.raises(Exception) as exc_info:
            extract_agent_response(response_data)

        assert "Agent error -1: Task failed" in str(exc_info.value)

    def test_extract_error_missing_code(self):
        """Test extracting error with missing code"""
        response_data = {"error": {"message": "Task failed"}}

        with pytest.raises(Exception) as exc_info:
            extract_agent_response(response_data)

        assert "Agent error unknown: Task failed" in str(exc_info.value)

    def test_extract_error_missing_message(self):
        """Test extracting error with missing message"""
        response_data = {"error": {"code": -1}}

        with pytest.raises(Exception) as exc_info:
            extract_agent_response(response_data)

        assert "Agent error -1: Unknown error" in str(exc_info.value)

    def test_extract_error_empty_error_object(self):
        """Test extracting empty error object"""
        response_data = {"error": {}}

        with pytest.raises(Exception) as exc_info:
            extract_agent_response(response_data)

        assert "Agent error unknown: Unknown error" in str(exc_info.value)

    def test_extract_no_result_or_error(self):
        """Test response with neither result nor error"""
        response_data = {"jsonrpc": "2.0", "id": 1}

        with pytest.raises(Exception) as exc_info:
            extract_agent_response(response_data)

        assert "Invalid A2A response: no result or error field" in str(exc_info.value)
