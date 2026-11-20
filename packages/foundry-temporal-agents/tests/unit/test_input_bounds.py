# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for STIG V-222612 input bounds on the activity call paths"""

from unittest.mock import AsyncMock, patch

import pytest
from foundry_temporal_agents import InputBoundsError, _limits
from foundry_temporal_agents.activities import (
    call_strands_agent_dataclass,
    strands_agent_activity,
    strands_agent_dataclass_activity,
)
from foundry_temporal_agents.models import StrandsAgentTaskInput
from foundry_temporal_agents.query_activities import _execute_query_call, strands_query_dataclass_activity
from foundry_temporal_agents.query_models import StrandsQueryTaskInput
from temporalio.exceptions import ApplicationError

OVER_KEYS = {f"k{i}": i for i in range(_limits.MAX_DICT_KEYS + 1)}


def _assert_invalid_input(exc_info: pytest.ExceptionInfo[ApplicationError], match: str) -> None:
    assert exc_info.value.type == "InvalidActivityInput"
    assert exc_info.value.non_retryable is True
    assert match in str(exc_info.value)


class TestAgentActivityBounds:
    """Test suite for bounds on the strands_agent_activity dict-return path."""

    @pytest.mark.parametrize(
        ("task_params", "match"),
        [
            ({"task": "x" * (_limits.MAX_TEXT_LEN + 1)}, "task exceeds maximum length"),
            pytest.param("x" * (_limits.MAX_TEXT_LEN + 1), "task exceeds maximum length", id="oversized-string"),
            ({"task": "t", "session_id": "s" * (_limits.MAX_SESSION_ID_LEN + 1)}, "session_id exceeds"),
            ({"task": "t", "context": OVER_KEYS}, "query_extra_data exceeds maximum"),
            ({"task": "t", **OVER_KEYS}, "additional_params exceeds maximum"),
            ({"task": "t", "context": {"blob": "x" * _limits.MAX_DICT_BYTES}}, "query_extra_data serializes above"),
            ({"task": ["x"] * 10}, "task must be a string"),
            ({"task": 12345}, "task must be a string"),
            ({"task": None}, "task must be a string"),
        ],
    )
    @pytest.mark.asyncio
    async def test_oversized_return_rejected_before_agent_call(self, task_params, match):
        """Test that an oversized built input raises a non-retryable error and never calls the agent."""

        @strands_agent_activity()
        async def build_task():
            return task_params

        with patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class:
            with pytest.raises(ApplicationError) as exc_info:
                await build_task("http://agent.com")

        _assert_invalid_input(exc_info, match)
        mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_oversized_worker_input_rejected_non_retryable(self):
        """Test that a wire dict failing StrandsAgentTaskInput bounds raises a non-retryable error."""

        @strands_agent_dataclass_activity()
        async def build_task(input_data: StrandsAgentTaskInput):
            return {"task": input_data.task}

        with pytest.raises(ApplicationError) as exc_info:
            await build_task("http://agent.com", {"task": "t", "additional_params": OVER_KEYS})

        _assert_invalid_input(exc_info, "additional_params exceeds maximum")


class TestQueryActivityBounds:
    """Test suite for bounds on the query activity dict-return path."""

    @pytest.mark.parametrize(
        ("task_params", "match"),
        [
            ({"query": "x" * (_limits.MAX_TEXT_LEN + 1)}, "query exceeds maximum length"),
            ({"query": "q", "session_id": "s" * (_limits.MAX_SESSION_ID_LEN + 1)}, "session_id exceeds"),
            ({"query": "q", "context": OVER_KEYS}, "context exceeds maximum"),
            ({"query": "q", **OVER_KEYS}, "additional_params exceeds maximum"),
            ({"query": "q", "max_results": 10**9}, "max_results must be between"),
            ({"query": "q", "max_results": 0}, "max_results must be between"),
            ({"query": "q", "max_results": float("inf")}, "max_results must be a finite number"),
            ({"query": "q", "max_results": 10**400}, "max_results must be between"),
            ({"query": "q", "max_results": 5.7}, "max_results must be a whole number"),
            ({"query": "q", "similarity_threshold": -5.0}, "similarity_threshold must be between"),
            ({"query": "q", "similarity_threshold": float("nan")}, "similarity_threshold must be a finite number"),
            ({"query": "q", "similarity_threshold": 10**400}, "similarity_threshold must be between"),
            ({"query": ["x"] * 10}, "query must be a string"),
            ({"query": None}, "query must be a string"),
        ],
    )
    @pytest.mark.asyncio
    async def test_oversized_return_rejected_before_query_call(self, task_params, match):
        """Test that an oversized built query raises a non-retryable error and never calls the agent."""
        with patch("foundry_temporal_agents.query_activities.StrandsQueryClient") as mock_client_class:
            with pytest.raises(ApplicationError) as exc_info:
                await _execute_query_call(
                    agent_url="http://test-agent:8000",
                    task_params=task_params,
                    timeout_seconds=300,
                    heartbeat_timeout_seconds=None,
                    validate_response=False,
                    wrapper_func=lambda: None,
                )

        _assert_invalid_input(exc_info, match)
        mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_oversized_worker_input_rejected_non_retryable(self):
        """Test that a wire dict failing StrandsQueryTaskInput validation raises a non-retryable error."""

        @strands_query_dataclass_activity()
        async def build_query(input_data: StrandsQueryTaskInput):
            return {"query": input_data.query}

        with pytest.raises(ApplicationError) as exc_info:
            await build_query("http://agent.com", {"query": "q", "context": OVER_KEYS})

        _assert_invalid_input(exc_info, "context exceeds maximum")


class TestInputBoundsError:
    """Test suite for the public InputBoundsError type."""

    def test_exported_and_is_value_error(self):
        """Test that InputBoundsError is public and still a ValueError."""
        import foundry_temporal_agents

        assert "InputBoundsError" in foundry_temporal_agents.__all__
        assert issubclass(InputBoundsError, ValueError)

    def test_dataclass_raises_input_bounds_error(self):
        """Test that StrandsAgentTaskInput raises InputBoundsError for an oversized field."""
        with pytest.raises(InputBoundsError, match="task exceeds maximum length"):
            StrandsAgentTaskInput(task="x" * (_limits.MAX_TEXT_LEN + 1))

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"task": 123}, "task must be a string"),
            ({"task": "t", "session_id": 42}, "session_id must be a string"),
        ],
    )
    def test_dataclass_requires_string_text(self, kwargs, match):
        """Test that StrandsAgentTaskInput rejects non-string task and session_id."""
        with pytest.raises(InputBoundsError, match=match):
            StrandsAgentTaskInput(**kwargs)


class TestSessionIdCountedSeparately:
    """Test suite for session_id travelling alongside the caller's additional_params."""

    @staticmethod
    async def _call(input_data: StrandsAgentTaskInput) -> AsyncMock:
        with (
            patch("foundry_temporal_agents.activities.StrandsAgentClient") as mock_client_class,
            patch("foundry_temporal_agents.activities.activity"),
        ):
            call_agent = AsyncMock(return_value={"status": "completed", "result": "ok"})
            mock_client_class.return_value.__aenter__.return_value.call_agent = call_agent
            await call_strands_agent_dataclass("http://agent.com", input_data)
        return call_agent

    @pytest.mark.asyncio
    async def test_additional_params_at_key_limit_with_session_id_accepted(self):
        """Test that a model accepted at the key limit is not rejected once the activity adds session_id."""
        params = {f"k{i}": i for i in range(_limits.MAX_DICT_KEYS)}
        call_agent = await self._call(StrandsAgentTaskInput(task="t", session_id="sess-1", additional_params=params))

        kwargs = call_agent.call_args.kwargs
        assert kwargs["session_id"] == "sess-1"
        assert {k: kwargs[k] for k in params} == params

    @pytest.mark.asyncio
    async def test_additional_params_at_byte_limit_with_session_id_accepted(self):
        """Test that a dict exactly at the byte limit is not pushed over it by session_id."""
        overhead = _limits.serialized_size({"blob": ""})
        params = {"blob": "x" * (_limits.MAX_DICT_BYTES - overhead)}
        assert _limits.serialized_size(params) == _limits.MAX_DICT_BYTES

        call_agent = await self._call(StrandsAgentTaskInput(task="t", session_id="sess-1", additional_params=params))
        assert call_agent.call_args.kwargs["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_session_id_bounded_as_text_on_activity_path(self):
        """Test that session_id is still bounded on the dict path, as text and not as a dict entry."""

        @strands_agent_activity()
        async def build_task():
            return {"task": "t", "session_id": "s" * (_limits.MAX_SESSION_ID_LEN + 1)}

        with patch("foundry_temporal_agents.activities.StrandsAgentClient"):
            with pytest.raises(ApplicationError, match="session_id exceeds maximum length"):
                await build_task("http://agent.com")
