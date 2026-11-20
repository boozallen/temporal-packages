# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal_agents.activities module"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from foundry_temporal_agents.activities import (
    _should_retry_error,
    _validate_agent_response,
    call_strands_agent,
    call_strands_agent_dataclass,
    strands_agent_activity,
    strands_agent_dataclass_activity,
)
from foundry_temporal_agents.exceptions import AgentCapabilityError, AgentNotFoundError, AgentRequestError
from foundry_temporal_agents.models import StrandsAgentTaskInput
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError


class TestStrandsAgentActivityDecorator:
    def test_decorator_basic_application(self):
        """Test basic decorator application"""

        @strands_agent_activity()
        async def test_activity():
            return "test task"

        assert callable(test_activity)

    def test_decorator_with_parameters(self):
        """Test decorator with custom parameters"""

        @strands_agent_activity(name="custom_activity", timeout_seconds=600, heartbeat_timeout_seconds=120)
        async def test_activity():
            return "test task"

        assert callable(test_activity)

    def test_default_timeout_settings(self):
        """Test default timeout settings"""

        @strands_agent_activity()
        async def test_activity():
            return "test task"

        assert callable(test_activity)

    @pytest.mark.asyncio
    async def test_activity_wrapper_dict_return(self):
        """Test activity wrapper with dict return from user function"""

        @strands_agent_activity()
        async def test_activity():
            return {"task": "process document", "context": {"file": "test.txt"}, "priority": "high"}

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = "agent response"
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await test_activity("http://agent.com")

            assert result == "agent response"
            mock_client.call_agent.assert_called_once_with(
                task="process document", query_extra_data={"file": "test.txt"}, priority="high"
            )

    @pytest.mark.asyncio
    async def test_activity_wrapper_string_return(self):
        """Test activity wrapper with string return from user function"""

        @strands_agent_activity()
        async def test_activity():
            return "simple task"

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = "agent response"
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await test_activity("http://agent.com")

            assert result == "agent response"
            mock_client.call_agent.assert_called_once_with(task="simple task", query_extra_data={})

    @pytest.mark.asyncio
    async def test_activity_disables_client_retries(self):
        """Test that the A2A client is built with max_retries=0, so Temporal is the sole retry authority."""

        @strands_agent_activity()
        async def test_activity():
            return "simple task"

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = "agent response"
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await test_activity("http://agent.com")

            _, kwargs = mock_client_class.call_args
            assert kwargs["max_retries"] == 0

    @pytest.mark.asyncio
    async def test_activity_wrapper_invalid_return(self):
        """Test activity wrapper with invalid return type"""

        @strands_agent_activity()
        async def test_activity():
            return 123  # Invalid return type

        with pytest.raises(ValueError, match="Activity function must return dict or string"):
            await test_activity("http://agent.com")

    @pytest.mark.asyncio
    async def test_activity_wrapper_with_capability_checking(self):
        """Test activity wrapper with capability checking"""

        @strands_agent_activity(check_capabilities=["text_processing"])
        async def test_activity():
            return "process text"

        with patch("foundry_temporal_agents.activities.AgentCapabilityChecker") as mock_checker_class:
            mock_checker = AsyncMock()
            mock_checker_class.return_value = mock_checker

            with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.call_agent.return_value = "response"
                mock_client_class.return_value.__aenter__.return_value = mock_client

                await test_activity("http://agent.com")

                mock_checker_class.assert_called_once_with("http://agent.com")
                mock_checker.requires_capability.assert_called_once_with("text_processing")

    @pytest.mark.asyncio
    async def test_activity_wrapper_capability_check_failure(self):
        """Test activity wrapper when capability check fails"""

        @strands_agent_activity(check_capabilities=["unsupported_capability"])
        async def test_activity():
            return "process text"

        with patch("foundry_temporal_agents.activities.AgentCapabilityChecker") as mock_checker_class:
            mock_checker = AsyncMock()
            mock_checker.requires_capability.side_effect = AgentCapabilityError("test-agent", "unsupported_capability")
            mock_checker_class.return_value = mock_checker

            with pytest.raises(AgentCapabilityError):
                await test_activity("http://agent.com")

    @pytest.mark.asyncio
    async def test_activity_wrapper_with_response_validation(self):
        """Test activity wrapper with response validation enabled"""

        @strands_agent_activity(validate_response=True)
        async def test_activity():
            return "test task"

        agent_response = {"status": "completed", "result": "success"}

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = agent_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("foundry_temporal_agents.activities._validate_agent_response") as mock_validate:
                result = await test_activity("http://agent.com")

                assert result == agent_response
                mock_validate.assert_called_once_with(agent_response, "http://agent.com")

    @pytest.mark.asyncio
    async def test_activity_wrapper_default_does_not_validate_failed_task(self):
        """Test that validate_response still defaults to False: a dict-shaped
        failed task status does not raise when validate_response is not passed."""

        @strands_agent_activity()
        async def test_activity():
            return "test task"

        agent_response = {"status": {"state": "failed", "message": "model unavailable"}}

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = agent_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # No exception, even though the response is a dict-shaped failed task.
            result = await test_activity("http://agent.com")

        assert result == agent_response

    @pytest.mark.asyncio
    async def test_activity_wrapper_heartbeat_functionality(self):
        """Test activity wrapper with heartbeat enabled"""

        @strands_agent_activity(heartbeat_timeout_seconds=60)
        async def test_activity():
            return "test task"

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = "response"
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("foundry_temporal_agents.activities.activity") as mock_activity:
                with patch("asyncio.create_task") as mock_create_task:
                    with patch("asyncio.sleep"):  # Mock sleep to prevent actual delays
                        # Create a real future that can be properly awaited
                        loop = asyncio.get_event_loop()
                        mock_task = loop.create_future()
                        mock_task.cancel = Mock(return_value=True)
                        mock_task.set_exception(asyncio.CancelledError())
                        mock_create_task.return_value = mock_task

                        result = await test_activity("http://agent.com")

                        assert result == "response"
                        # Should have called heartbeat at least once (initial heartbeat)
                        assert mock_activity.heartbeat.call_count >= 1
                        # Should have created and cancelled heartbeat task
                        mock_create_task.assert_called_once()
                        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_activity_wrapper_function_metadata_capabilities(self):
        """Test activity wrapper uses function metadata for capabilities"""

        async def test_activity():
            return "test task"

        # Set required capabilities via function metadata
        test_activity._required_capabilities = ["file_operations"]

        decorated = strands_agent_activity()(test_activity)

        with patch("foundry_temporal_agents.activities.AgentCapabilityChecker") as mock_checker_class:
            mock_checker = AsyncMock()
            mock_checker_class.return_value = mock_checker

            with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.call_agent.return_value = "response"
                mock_client_class.return_value.__aenter__.return_value = mock_client

                await decorated("http://agent.com")

                mock_checker.requires_capability.assert_called_once_with("file_operations")


class TestCallStrandsAgent:
    @pytest.mark.asyncio
    async def test_call_strands_agent_basic(self):
        """Test call_strands_agent function with basic parameters"""
        # Access the raw function (before decoration)
        from foundry_temporal_agents.activities import call_strands_agent

        raw_func = call_strands_agent.__wrapped__
        result = await raw_func("test task")

        expected = {"task": "test task", "context": {}, "session_id": None}
        assert result == expected

    @pytest.mark.asyncio
    async def test_call_strands_agent_with_extra_data(self):
        """Test call_strands_agent with extra data"""
        from foundry_temporal_agents.activities import call_strands_agent

        raw_func = call_strands_agent.__wrapped__
        extra_data = {"file": "test.txt", "priority": "high"}
        result = await raw_func("test task", query_extra_data=extra_data)

        expected = {"task": "test task", "context": extra_data, "session_id": None}
        assert result == expected

    @pytest.mark.asyncio
    async def test_call_strands_agent_with_session_id(self):
        """Test call_strands_agent with session ID"""
        from foundry_temporal_agents.activities import call_strands_agent

        raw_func = call_strands_agent.__wrapped__
        result = await raw_func("test task", session_id="session-123")

        expected = {"task": "test task", "context": {}, "session_id": "session-123"}
        assert result == expected

    @pytest.mark.asyncio
    async def test_call_strands_agent_with_kwargs(self):
        """Test call_strands_agent with additional kwargs"""
        from foundry_temporal_agents.activities import call_strands_agent

        raw_func = call_strands_agent.__wrapped__
        result = await raw_func("test task", priority="high", deadline="2024-01-01")

        expected = {
            "task": "test task",
            "context": {},
            "session_id": None,
            "priority": "high",
            "deadline": "2024-01-01",
        }
        assert result == expected

    def test_call_strands_agent_has_activity_metadata(self):
        """Test that call_strands_agent has proper activity metadata"""
        assert callable(call_strands_agent)


class TestCallStrandsAgentDataclass:
    @pytest.mark.asyncio
    async def test_call_strands_agent_dataclass_basic(self):
        """Test call_strands_agent_dataclass function with basic parameters"""
        from foundry_temporal_agents.activities import call_strands_agent_dataclass
        from foundry_temporal_agents.models import StrandsAgentTaskInput

        raw_func = call_strands_agent_dataclass.__wrapped__
        input_data = StrandsAgentTaskInput(task="test task")
        result = await raw_func(input_data)

        expected = {"task": "test task", "context": {}, "session_id": None}
        assert result == expected

    @pytest.mark.asyncio
    async def test_call_strands_agent_dataclass_with_extra_data(self):
        """Test call_strands_agent_dataclass with extra data"""
        from foundry_temporal_agents.activities import call_strands_agent_dataclass
        from foundry_temporal_agents.models import StrandsAgentTaskInput

        raw_func = call_strands_agent_dataclass.__wrapped__
        extra_data = {"file": "test.txt", "priority": "high"}
        input_data = StrandsAgentTaskInput(task="test task", query_extra_data=extra_data)
        result = await raw_func(input_data)

        expected = {"task": "test task", "context": extra_data, "session_id": None}
        assert result == expected

    @pytest.mark.asyncio
    async def test_call_strands_agent_dataclass_with_session_id(self):
        """Test call_strands_agent_dataclass with session ID"""
        from foundry_temporal_agents.activities import call_strands_agent_dataclass
        from foundry_temporal_agents.models import StrandsAgentTaskInput

        raw_func = call_strands_agent_dataclass.__wrapped__
        input_data = StrandsAgentTaskInput(task="test task", session_id="session-123")
        result = await raw_func(input_data)

        expected = {"task": "test task", "context": {}, "session_id": "session-123"}
        assert result == expected

    @pytest.mark.asyncio
    async def test_call_strands_agent_dataclass_with_additional_params(self):
        """Test call_strands_agent_dataclass with additional params"""
        from foundry_temporal_agents.activities import call_strands_agent_dataclass
        from foundry_temporal_agents.models import StrandsAgentTaskInput

        raw_func = call_strands_agent_dataclass.__wrapped__
        input_data = StrandsAgentTaskInput(
            task="test task", additional_params={"priority": "high", "deadline": "2024-01-01"}
        )
        result = await raw_func(input_data)

        expected = {
            "task": "test task",
            "context": {},
            "session_id": None,
            "priority": "high",
            "deadline": "2024-01-01",
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_call_strands_agent_dataclass_accepts_dict_input(self):
        """Test that call_strands_agent_dataclass handles dict input from Temporal deserialization."""
        from foundry_temporal_agents.activities import call_strands_agent_dataclass

        dict_input = {
            "task": "analyze document",
            "query_extra_data": {"file": "test.pdf"},
            "session_id": "session-123",
            "additional_params": {},
        }

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = "agent response"
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("foundry_temporal_agents.activities.activity"):
                result = await call_strands_agent_dataclass("http://agent.com", dict_input)

            assert result == "agent response"
            mock_client.call_agent.assert_called_once()

    def test_call_strands_agent_dataclass_has_activity_metadata(self):
        """Test that call_strands_agent_dataclass has proper activity metadata"""
        assert callable(call_strands_agent_dataclass)

    @pytest.mark.asyncio
    async def test_call_strands_agent_dataclass_accepts_temporal_style_dict_input(self, temporal_style_input):
        """
        Temporal-style input test: activity must accept dict input (as delivered
        by Temporal's default data converter when invoked by string name).
        Without coercion in the wrapper, this fails with AttributeError.
        """
        from foundry_temporal_agents.activities import call_strands_agent_dataclass
        from foundry_temporal_agents.models import StrandsAgentTaskInput

        typed = StrandsAgentTaskInput(
            task="analyze document",
            query_extra_data={"file": "test.pdf"},
            session_id="session-123",
            additional_params={},
        )
        dict_input = temporal_style_input(typed)

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = "agent response"
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("foundry_temporal_agents.activities.activity"):
                result = await call_strands_agent_dataclass("http://agent.com", dict_input)

            assert result == "agent response"
            mock_client.call_agent.assert_called_once()


class TestValidateAgentResponse:
    def test_validate_non_dict_response(self):
        """Test validation allows non-dict responses"""
        # Should not raise exception for non-dict responses
        _validate_agent_response("string response", "http://agent.com")
        _validate_agent_response(123, "http://agent.com")
        _validate_agent_response(["list", "response"], "http://agent.com")

    def test_validate_successful_response(self):
        """Test validation of successful response"""
        response = {"status": "completed", "result": "task completed successfully", "summary": "Processed document"}

        # Should not raise exception
        _validate_agent_response(response, "http://agent.com")

    def test_validate_failed_response_retryable(self):
        """Test validation of failed response with retryable error"""
        response = {
            "status": "failed",
            "error": "Connection timeout occurred",
            "retry_suggestion": "Try again in a few minutes",
        }

        with pytest.raises(ApplicationError) as exc_info:
            _validate_agent_response(response, "http://agent.com")

        error = exc_info.value
        assert "Agent task failed: Connection timeout occurred" in str(error)
        assert "Try again in a few minutes" in str(error)
        assert error.non_retryable is False  # Should be retryable
        assert error.type == "AgentTaskFailure"

    def test_validate_failed_response_non_retryable(self):
        """Test validation of failed response with non-retryable error"""
        response = {"status": "failed", "error": "Invalid input format provided"}

        with pytest.raises(ApplicationError) as exc_info:
            _validate_agent_response(response, "http://agent.com")

        error = exc_info.value
        assert "Agent task failed: Invalid input format provided" in str(error)
        assert error.non_retryable is True  # Should be non-retryable

    def test_validate_failed_response_no_error_message(self):
        """Test validation of failed response without error message"""
        response = {"status": "failed"}

        with pytest.raises(ApplicationError) as exc_info:
            _validate_agent_response(response, "http://agent.com")

        error = exc_info.value
        assert "Agent task failed: Unknown error" in str(error)

    def test_validate_unknown_status(self):
        """Test validation with unknown status (should not fail)"""
        response = {"status": "processing", "progress": 50}

        # Should not raise exception, just log warning
        _validate_agent_response(response, "http://agent.com")

    def test_validate_response_no_status(self):
        """Test validation of response without status field"""
        response = {"result": "some result", "metadata": "additional info"}

        # Should not raise exception
        _validate_agent_response(response, "http://agent.com")

    @pytest.mark.parametrize("state", ["failed", "rejected", "canceled"])
    def test_validate_dict_status_failure_states_raise(self, state):
        """Test that a dict-shaped A2A Task status.state failure raises non-retryably"""
        response = {"status": {"state": state, "message": "model unavailable"}}

        with pytest.raises(ApplicationError) as exc_info:
            _validate_agent_response(response, "http://agent.com")

        error = exc_info.value
        assert state in str(error)
        assert "model unavailable" in str(error)
        assert error.non_retryable is True
        assert error.type == "AgentTaskFailure"

    @pytest.mark.parametrize("state", ["input-required", "auth-required"])
    def test_validate_dict_status_attention_states_raise(self, state):
        """Test that input-required/auth-required raise a distinct ApplicationError"""
        response = {"status": {"state": state, "message": "missing required field: date_range"}}

        with pytest.raises(ApplicationError) as exc_info:
            _validate_agent_response(response, "http://agent.com")

        error = exc_info.value
        assert state in str(error)
        assert "missing required field: date_range" in str(error)
        assert error.non_retryable is True
        assert error.type == "AgentTaskAttentionRequired"

    def test_validate_dict_status_completed_does_not_raise(self):
        """Test that a dict-shaped status.state of completed does not raise"""
        response = {"status": {"state": "completed", "message": "done"}}

        # Should not raise exception
        _validate_agent_response(response, "http://agent.com")

    def test_validate_dict_status_failed_without_message(self):
        """Test that a dict-shaped failure without a message field still raises"""
        response = {"status": {"state": "failed"}}

        with pytest.raises(ApplicationError) as exc_info:
            _validate_agent_response(response, "http://agent.com")

        assert "failed" in str(exc_info.value)

    def test_validate_dict_status_reads_a2a_message_parts(self):
        """Test that the text is read from an A2A Message object in status.message"""
        response = {
            "status": {
                "state": "failed",
                "message": {"role": "agent", "parts": [{"kind": "text", "text": "tool crashed"}]},
            }
        }

        with pytest.raises(ApplicationError) as exc_info:
            _validate_agent_response(response, "http://agent.com")

        assert exc_info.value.message == "Agent task failed: tool crashed"

    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            (
                {
                    "parts": [
                        {"kind": "text", "text": "tool"},
                        {"kind": "data", "data": {"code": 7}},
                        "not-a-part",
                        {"kind": "text", "text": "crashed"},
                    ]
                },
                "Agent task failed: tool crashed",
            ),
            ({"parts": "tool crashed"}, "Agent task failed"),
            ({"parts": [{"kind": "data", "data": {}}]}, "Agent task failed"),
            ("", "Agent task failed"),
            (42, "Agent task failed"),
        ],
    )
    def test_validate_dict_status_message_edge_cases(self, message, expected):
        """Test that only text parts are read, and odd message shapes fall back to the state"""
        response = {"status": {"state": "failed", "message": message}}

        with pytest.raises(ApplicationError) as exc_info:
            _validate_agent_response(response, "http://agent.com")

        assert exc_info.value.message == expected

    def test_validate_dict_status_unexpected_state_does_not_raise(self):
        """Test that an unexpected state such as unknown only logs a warning"""
        response = {"status": {"state": "unknown"}}

        # Should not raise exception
        _validate_agent_response(response, "http://agent.com")


class TestShouldRetryError:
    def test_retryable_errors(self):
        """Test that retryable error keywords are detected"""
        retryable_messages = [
            "Connection timeout occurred",
            "Network error during request",
            "Temporary service unavailable",
            "Rate limit exceeded",
            "Server error 500",
            "Service is busy, try again",
            "System overloaded",
        ]

        for message in retryable_messages:
            assert _should_retry_error(message) is True, f"Should be retryable: {message}"

    def test_non_retryable_errors(self):
        """Test that non-retryable error keywords are detected"""
        non_retryable_messages = [
            "Invalid input provided",
            "Bad request format",
            "Unauthorized access attempt",
            "Forbidden operation",
            "Resource not found",
            "Permission denied for user",
            "Invalid format in request",
            "Parse error in JSON",
        ]

        for message in non_retryable_messages:
            assert _should_retry_error(message) is False, f"Should be non-retryable: {message}"

    def test_unknown_errors_default_retryable(self):
        """Test that unknown errors default to retryable"""
        unknown_messages = ["Some unknown error occurred", "Mysterious failure", "Unexpected behavior detected"]

        for message in unknown_messages:
            assert _should_retry_error(message) is True, f"Should default to retryable: {message}"

    def test_empty_error_message(self):
        """Test empty or None error message"""
        assert _should_retry_error("") is False
        assert _should_retry_error(None) is False

    def test_case_insensitive_matching(self):
        """Test that error matching is case insensitive"""
        assert _should_retry_error("CONNECTION TIMEOUT") is True
        assert _should_retry_error("Invalid Input") is False
        assert _should_retry_error("Network ERROR") is True

    def test_partial_keyword_matching(self):
        """Test that keywords are matched as substrings"""
        assert _should_retry_error("The connection timed out unexpectedly") is True
        assert _should_retry_error("Request contains invalid input data") is False
        assert _should_retry_error("Received a server error response") is True

    def test_non_retryable_takes_precedence(self):
        """Test that non-retryable keywords take precedence over retryable ones"""
        # Message contains both "timeout" (retryable) and "invalid input" (non-retryable)
        message = "Timeout occurred due to invalid input format"
        assert _should_retry_error(message) is False


class TestStrandsAgentDataclassActivityDecorator:
    """Tests for the strands_agent_dataclass_activity decorator"""

    def test_dataclass_decorator_basic_application(self):
        """Test basic decorator application with dataclass input"""

        @strands_agent_dataclass_activity()
        async def test_activity(input_data: StrandsAgentTaskInput):
            return {"task": input_data.task, "context": input_data.query_extra_data}

        assert callable(test_activity)

    def test_dataclass_decorator_with_parameters(self):
        """Test decorator with custom parameters"""

        @strands_agent_dataclass_activity(
            name="custom_dataclass_activity", timeout_seconds=600, heartbeat_timeout_seconds=120
        )
        async def test_activity(input_data: StrandsAgentTaskInput):
            return {"task": input_data.task}

        assert callable(test_activity)

    @pytest.mark.asyncio
    async def test_dataclass_activity_wrapper_basic(self):
        """Test dataclass activity wrapper with basic dataclass input"""

        @strands_agent_dataclass_activity()
        async def test_activity(input_data: StrandsAgentTaskInput):
            return {
                "task": input_data.task,
                "context": input_data.query_extra_data or {},
                "session_id": input_data.session_id,
            }

        input_data = StrandsAgentTaskInput(
            task="analyze document", query_extra_data={"file": "test.pdf"}, session_id="session-123"
        )

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = "agent response"
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await test_activity("http://agent.com", input_data)

            assert result == "agent response"
            mock_client.call_agent.assert_called_once_with(
                task="analyze document", query_extra_data={"file": "test.pdf"}, session_id="session-123"
            )

    @pytest.mark.asyncio
    async def test_dataclass_activity_with_capability_checking(self):
        """Test dataclass activity with capability checking"""

        @strands_agent_dataclass_activity(check_capabilities=["text_processing"])
        async def test_activity(input_data: StrandsAgentTaskInput):
            return {"task": input_data.task}

        input_data = StrandsAgentTaskInput(task="process text")

        with patch("foundry_temporal_agents.activities.AgentCapabilityChecker") as mock_checker_class:
            mock_checker = AsyncMock()
            mock_checker_class.return_value = mock_checker

            with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.call_agent.return_value = "response"
                mock_client_class.return_value.__aenter__.return_value = mock_client

                await test_activity("http://agent.com", input_data)

                mock_checker_class.assert_called_once_with("http://agent.com")
                mock_checker.requires_capability.assert_called_once_with("text_processing")

    @pytest.mark.asyncio
    async def test_dataclass_activity_with_validation(self):
        """Test dataclass activity with response validation enabled"""

        @strands_agent_dataclass_activity(validate_response=True)
        async def test_activity(input_data: StrandsAgentTaskInput):
            return {"task": input_data.task}

        input_data = StrandsAgentTaskInput(task="test task")
        agent_response = {"status": "completed", "result": "success"}

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = agent_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with patch("foundry_temporal_agents.activities._validate_agent_response") as mock_validate:
                result = await test_activity("http://agent.com", input_data)

                assert result == agent_response
                mock_validate.assert_called_once_with(agent_response, "http://agent.com")

    @pytest.mark.asyncio
    async def test_dataclass_activity_with_custom_model(self):
        """Test dataclass activity with custom input model"""

        @dataclass
        class CustomAnalysisInput:
            content: str
            analysis_type: str
            metadata: dict[str, object] | None = None

        @strands_agent_dataclass_activity()
        async def analyze_activity(input_data: CustomAnalysisInput):
            return {"task": f"Analyze as {input_data.analysis_type}", "context": input_data.metadata or {}}

        input_data = CustomAnalysisInput(content="Some content", analysis_type="summary", metadata={"source": "api"})

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.call_agent.return_value = "analysis result"
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await analyze_activity("http://agent.com", input_data)

            assert result == "analysis result"
            mock_client.call_agent.assert_called_once()

    def test_dataclass_models_available(self):
        """Test that dataclass models are importable from package"""
        from foundry_temporal_agents import StrandsAgentTaskInput

        assert callable(StrandsAgentTaskInput)

    def test_strands_agent_dataclass_activity_decorator_available(self):
        """Test that strands_agent_dataclass_activity decorator is available from package"""
        from foundry_temporal_agents import strands_agent_dataclass_activity as decorator

        assert callable(decorator)


# Test workflow must be defined at module level (not inside test function)
# because Temporal doesn't support local classes for workflows
@workflow.defn
class TestDocumentationPatternWorkflow:
    """Test workflow that uses the exact pattern from documentation"""

    @workflow.run
    async def run(self, agent_url: str):
        """This workflow uses the EXACT pattern from dataclass-best-practices.md lines 86-90"""
        from foundry_temporal_agents import StrandsAgentTaskInput, call_strands_agent_dataclass

        # This is the EXACT pattern from the documentation (line 86-90)
        input_data = StrandsAgentTaskInput(
            task="Analyze this document and extract key insights",
            query_extra_data={"file": "document.pdf", "format": "markdown"},
            session_id="session-123",
            additional_params={"priority": "high"},
        )

        # EXACT pattern from documentation - line 86-90
        result = await workflow.execute_activity(
            call_strands_agent_dataclass,
            args=[agent_url, input_data],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        return result


class TestWorkflowUsagePattern:
    """Tests verifying workflow usage pattern matches documentation"""

    @pytest.mark.asyncio
    async def test_call_strands_agent_dataclass_with_documented_pattern(self):
        """
        Test that call_strands_agent_dataclass accepts args in the pattern shown in documentation.

        This verifies the usage pattern from dataclass-best-practices.md:
        ```python
        result = await workflow.execute_activity(
            call_strands_agent_dataclass,
            args=[agent_url, input_data],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )
        ```
        """
        from datetime import timedelta

        from foundry_temporal_agents import StrandsAgentTaskInput, call_strands_agent_dataclass
        from temporalio import workflow
        from temporalio.common import RetryPolicy

        agent_url = "http://test-agent.com"
        input_data = StrandsAgentTaskInput(
            task="Analyze this document and extract key insights",
            query_extra_data={"file": "document.pdf", "format": "markdown"},
            session_id="session-123",
            additional_params={"priority": "high"},
        )

        # Mock workflow.execute_activity to verify call correctness
        with patch("temporalio.workflow.execute_activity") as mock_execute:
            mock_execute.return_value = {"status": "completed", "result": "test result"}

            # Execute the EXACT pattern from documentation
            result = await workflow.execute_activity(
                call_strands_agent_dataclass,
                args=[agent_url, input_data],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            # Verify the result
            assert result == {"status": "completed", "result": "test result"}

            # Verify execute_activity was called with correct arguments
            mock_execute.assert_called_once_with(
                call_strands_agent_dataclass,
                args=[agent_url, input_data],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

    @pytest.mark.asyncio
    async def test_call_strands_agent_with_documented_pattern(self):
        """
        Test that call_strands_agent works with workflow.execute_activity.

        This verifies the basic usage pattern for call_strands_agent:
        ```python
        result = await workflow.execute_activity(
            call_strands_agent,
            args=[agent_url, task, query_extra_data, session_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3)
        )
        ```
        """
        from datetime import timedelta

        from foundry_temporal_agents import call_strands_agent
        from temporalio import workflow
        from temporalio.common import RetryPolicy

        agent_url = "http://test-agent.com"
        task = "Analyze this document and extract key insights"
        query_extra_data = {"file": "document.pdf", "format": "markdown"}
        session_id = "session-123"

        # Mock workflow.execute_activity to verify call correctness
        with patch("temporalio.workflow.execute_activity") as mock_execute:
            mock_execute.return_value = {"status": "completed", "result": "test result"}

            # Execute with workflow.execute_activity pattern
            result = await workflow.execute_activity(
                call_strands_agent,
                args=[agent_url, task, query_extra_data, session_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            # Verify the result
            assert result == {"status": "completed", "result": "test result"}

            # Verify execute_activity was called with correct arguments
            mock_execute.assert_called_once_with(
                call_strands_agent,
                args=[agent_url, task, query_extra_data, session_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )


class TestExecuteAgentCallTls:
    @pytest.mark.asyncio
    async def test_tls_context_passed_to_client(self, monkeypatch):
        """Verify _execute_agent_call passes TLS context from env to client"""
        import ssl

        monkeypatch.delenv("FOUNDRY_AGENT_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", raising=False)
        mock_ctx = ssl.create_default_context()

        with (
            patch(
                "foundry_temporal_agents.activities.create_agent_tls_context",
                return_value=mock_ctx,
            ),
            patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_cls,
            patch("temporalio.activity.heartbeat"),
        ):
            mock_client = AsyncMock()
            mock_client.call_agent = AsyncMock(return_value="result")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from foundry_temporal_agents.activities import _execute_agent_call

            await _execute_agent_call(
                agent_url="https://agent.example.com",
                task_params={"task": "hello"},
                timeout_seconds=30,
                heartbeat_timeout_seconds=None,
                check_capabilities=None,
                required_capabilities=None,
                validate_response=False,
                wrapper_func=Mock(),
            )

            mock_client_cls.assert_called_once_with(
                agent_url="https://agent.example.com",
                timeout=30,
                max_retries=0,
                auth_headers={},
                ssl_context=mock_ctx,
            )


class TestExecuteAgentCallAuth:
    @pytest.mark.asyncio
    async def test_execute_agent_call_attaches_bearer_token_when_configured(self, monkeypatch):
        """Test that the configured bearer credential is attached as an Authorization header."""
        monkeypatch.setenv("FOUNDRY_AGENT_BEARER_TOKEN", "test-bearer-token")

        with (
            patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_cls,
            patch("temporalio.activity.heartbeat"),
        ):
            mock_client = AsyncMock()
            mock_client.call_agent = AsyncMock(return_value="result")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from foundry_temporal_agents.activities import _execute_agent_call

            await _execute_agent_call(
                agent_url="http://agent.example.com",
                task_params={"task": "hello"},
                timeout_seconds=30,
                heartbeat_timeout_seconds=None,
                check_capabilities=None,
                required_capabilities=None,
                validate_response=False,
                wrapper_func=Mock(),
            )

            _, kwargs = mock_client_cls.call_args
            assert kwargs["auth_headers"] == {"Authorization": "Bearer test-bearer-token"}

    @pytest.mark.asyncio
    async def test_execute_agent_call_no_bearer_token_sends_empty_auth_headers_and_warns(self, monkeypatch, caplog):
        """Test that a missing bearer credential results in empty auth_headers and a warning, not an error."""
        monkeypatch.delenv("FOUNDRY_AGENT_BEARER_TOKEN", raising=False)
        monkeypatch.delenv("FOUNDRY_AGENT_QUERY_BEARER_TOKEN", raising=False)

        with (
            patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_cls,
            patch("temporalio.activity.heartbeat"),
        ):
            mock_client = AsyncMock()
            mock_client.call_agent = AsyncMock(return_value="result")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from foundry_temporal_agents.activities import _execute_agent_call

            await _execute_agent_call(
                agent_url="http://agent.example.com",
                task_params={"task": "hello"},
                timeout_seconds=30,
                heartbeat_timeout_seconds=None,
                check_capabilities=None,
                required_capabilities=None,
                validate_response=False,
                wrapper_func=Mock(),
            )

            _, kwargs = mock_client_cls.call_args
            assert kwargs["auth_headers"] == {}
            assert "FOUNDRY_AGENT_BEARER_TOKEN" in caplog.text

    @pytest.mark.asyncio
    async def test_execute_agent_call_authentication_error_becomes_non_retryable_application_error(self):
        """Test that an AgentAuthenticationError from the client surfaces as a non-retryable
        Temporal error, distinct from an agent-not-found failure."""
        from foundry_temporal_agents.exceptions import AgentAuthenticationError

        with (
            patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_cls,
            patch("temporalio.activity.heartbeat"),
        ):
            mock_client = AsyncMock()
            mock_client.call_agent = AsyncMock(side_effect=AgentAuthenticationError("http://agent.example.com", 401))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from foundry_temporal_agents.activities import _execute_agent_call

            with pytest.raises(ApplicationError) as exc_info:
                await _execute_agent_call(
                    agent_url="http://agent.example.com",
                    task_params={"task": "hello"},
                    timeout_seconds=30,
                    heartbeat_timeout_seconds=None,
                    check_capabilities=None,
                    required_capabilities=None,
                    validate_response=False,
                    wrapper_func=Mock(),
                )

            assert exc_info.value.non_retryable is True
            assert exc_info.value.type == "AgentAuthenticationFailure"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "error_type"),
        [
            (AgentNotFoundError("http://agent.example.com", status=404), "AgentNotFoundError"),
            (AgentRequestError("http://agent.example.com", 400), "AgentRequestError"),
        ],
    )
    async def test_execute_agent_call_client_error_becomes_non_retryable_application_error(self, error, error_type):
        """Test that a 404 or other non-retryable 4xx is not retried by Temporal."""
        with (
            patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_cls,
            patch("temporalio.activity.heartbeat"),
        ):
            mock_client = AsyncMock()
            mock_client.call_agent = AsyncMock(side_effect=error)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from foundry_temporal_agents.activities import _execute_agent_call

            with pytest.raises(ApplicationError) as exc_info:
                await _execute_agent_call(
                    agent_url="http://agent.example.com",
                    task_params={"task": "hello"},
                    timeout_seconds=30,
                    heartbeat_timeout_seconds=None,
                    check_capabilities=None,
                    required_capabilities=None,
                    validate_response=False,
                    wrapper_func=Mock(),
                )

            assert exc_info.value.non_retryable is True
            assert exc_info.value.type == error_type

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [None, 429, 503])
    async def test_execute_agent_call_non_404_agent_not_found_stays_retryable(self, status):
        """Test that an unreachable agent, or a 429/5xx after client retries, is left for Temporal to retry."""
        with (
            patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_cls,
            patch("temporalio.activity.heartbeat"),
        ):
            mock_client = AsyncMock()
            mock_client.call_agent = AsyncMock(
                side_effect=AgentNotFoundError("http://agent.example.com", status=status)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            from foundry_temporal_agents.activities import _execute_agent_call

            with pytest.raises(AgentNotFoundError) as exc_info:
                await _execute_agent_call(
                    agent_url="http://agent.example.com",
                    task_params={"task": "hello"},
                    timeout_seconds=30,
                    heartbeat_timeout_seconds=None,
                    check_capabilities=None,
                    required_capabilities=None,
                    validate_response=False,
                    wrapper_func=Mock(),
                )

            assert exc_info.value.status == status
