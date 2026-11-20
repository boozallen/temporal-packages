# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Temporal activity helpers for Strands agent calls."""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, cast, get_type_hints

from temporalio import activity
from temporalio.exceptions import ApplicationError

from ._limits import enforce_activity_input_bounds
from .auth import build_agent_auth_headers
from .client import StrandsAgentClient
from .discovery import AgentCapabilityChecker
from .exceptions import AgentAuthenticationError, AgentNotFoundError, AgentRequestError
from .models import StrandsAgentTaskInput
from .tls import create_agent_tls_context

logger = logging.getLogger(__name__)

type TaskResult = str | dict[str, object]


def _resolve_first_param_type(func: Callable) -> type | None:
    """Resolve the type annotation of the first parameter of *func*.

    Used at decoration time so the wrapper can reconstruct a dataclass
    from a plain dict when Temporal deserialises the activity argument.
    """
    try:
        hints = get_type_hints(func)
        first_param = next(iter(inspect.signature(func).parameters))
        return hints.get(first_param)
    except Exception:
        return None


def _coerce_input(input_data: Any, expected_type: type | None) -> Any:
    """If *input_data* arrived as a dict but *expected_type* is a class, reconstruct it."""
    if not isinstance(input_data, dict) or expected_type is None:
        return input_data
    try:
        if hasattr(expected_type, "model_validate"):
            return expected_type.model_validate(input_data)
        return expected_type(**input_data)
    except ValueError as e:
        # Includes pydantic ValidationError and STIG V-222612 bound violations.
        # Non-retryable because the same input fails the same way on every attempt.
        raise ApplicationError(str(e), non_retryable=True, type="InvalidActivityInput") from e


async def _execute_agent_call(
    agent_url: str,
    task_params: TaskResult,
    timeout_seconds: int,
    heartbeat_timeout_seconds: int | None,
    check_capabilities: list[str] | None,
    required_capabilities: list[str] | None,
    validate_response: bool,
    wrapper_func: Callable,
) -> object:
    """
    Shared logic for executing Strands agent calls.

    This extracts the common agent calling logic used by both
    strands_agent_activity and strands_agent_dataclass_activity.

    Args:
        agent_url: URL of the Strands agent endpoint
        task_params: Task parameters from the wrapped function
        timeout_seconds: HTTP timeout
        heartbeat_timeout_seconds: Heartbeat configuration
        check_capabilities: Capabilities to check from decorator
        required_capabilities: Capabilities from function metadata
        validate_response: Whether to validate response
        wrapper_func: The wrapper function (for accessing metadata)

    Returns:
        Raw agent response from StrandsAgentClient.call_agent
    """
    # Check capabilities
    capabilities_to_check = check_capabilities or required_capabilities
    if capabilities_to_check:
        capability_checker = AgentCapabilityChecker(agent_url)
        for capability in capabilities_to_check:
            await capability_checker.requires_capability(capability)
            logger.info(f"Verified agent capability: {capability}")

    # Extract task and extra data from function result
    task_params_obj: object = task_params
    if isinstance(task_params_obj, dict):
        task_obj: object = task_params_obj.get("task", "")

        context_obj = task_params_obj.get("context", {})
        query_extra_data = cast(dict[str, object], context_obj) if isinstance(context_obj, dict) else {}

        additional_params = {k: v for k, v in task_params_obj.items() if k not in ["task", "context"]}
    elif isinstance(task_params_obj, str):
        task_obj = task_params_obj
        query_extra_data = {}
        additional_params = {}
    else:
        raise ValueError("Activity function must return dict or string")

    # session_id travels in the same dict as the caller's parameters, so take it out
    # first and bound it as text. The caller's parameters are then counted exactly as
    # StrandsAgentTaskInput counted them.
    session_id_obj = additional_params.pop("session_id", None)
    enforce_activity_input_bounds(
        task_obj,
        "task",
        session_id_obj,
        {"query_extra_data": query_extra_data, "additional_params": additional_params},
    )
    task = cast(str, task_obj)
    session_id = session_id_obj if isinstance(session_id_obj, str) else None

    # Set up continuous heartbeat if configured
    heartbeat_task = None
    if heartbeat_timeout_seconds:

        async def periodic_heartbeat():
            assert heartbeat_timeout_seconds is not None
            heartbeat_interval = max(1, heartbeat_timeout_seconds // 4)
            while True:
                await asyncio.sleep(heartbeat_interval)
                activity.heartbeat(f"Agent call in progress: {agent_url}")

        heartbeat_task = asyncio.create_task(periodic_heartbeat())
        activity.heartbeat(f"Starting agent call: {agent_url}")

    # Attach the bearer credential the agent's auth middleware validates.
    auth_headers = build_agent_auth_headers(agent_url)

    try:
        # Call the Strands agent. max_retries=0 for the same reason as the query
        # activities: the Temporal activity retry policy is the sole retry
        # authority, so an inner retry loop would compound with it.
        ssl_context = create_agent_tls_context()
        async with StrandsAgentClient(
            agent_url=agent_url,
            timeout=timeout_seconds,
            max_retries=0,
            auth_headers=auth_headers,
            ssl_context=ssl_context,
        ) as client:
            try:
                if session_id is None:
                    result = await client.call_agent(
                        task=task,
                        query_extra_data=query_extra_data,
                        **additional_params,
                    )
                else:
                    result = await client.call_agent(
                        task=task,
                        query_extra_data=query_extra_data,
                        session_id=session_id,
                        **additional_params,
                    )
            except AgentAuthenticationError as e:
                raise ApplicationError(str(e), non_retryable=True, type="AgentAuthenticationFailure") from e
            except AgentNotFoundError as e:
                # Only a 404 is permanent. Unreachable agents stay retryable.
                if e.status == 404:
                    raise ApplicationError(str(e), non_retryable=True, type="AgentNotFoundError") from e
                raise
            except AgentRequestError as e:
                raise ApplicationError(str(e), non_retryable=True, type="AgentRequestError") from e

            # Validate agent response if enabled
            if validate_response:
                _validate_agent_response(result, agent_url)

            # Send final heartbeat
            if heartbeat_timeout_seconds:
                activity.heartbeat("Agent call completed successfully")

            logger.info("Strands agent activity completed")
            return result

    finally:
        # Stop heartbeat task
        if heartbeat_task:
            _ = heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass


def strands_agent_activity(
    name: str | None = None,
    timeout_seconds: int = 300,
    heartbeat_timeout_seconds: int | None = None,
    check_capabilities: list[str] | None = None,
    validate_response: bool = False,
):
    """
    Decorate an async function that builds a task payload for a Strands agent.

    Args:
        name: Temporal activity name. Defaults to the function name.
        timeout_seconds: HTTP timeout (seconds) used by `StrandsAgentClient`.
        heartbeat_timeout_seconds: If set, enables periodic activity heartbeats.
            Heartbeats are sent every `max(1, heartbeat_timeout_seconds // 4)`.
        check_capabilities: Optional required capabilities to validate before calling.
        validate_response: If True, validates structured agent failure responses.

    Returns:
        Temporal activity function that accepts `agent_url` as the first arg,
        then forwards the remaining args/kwargs to the wrapped function.
    """

    def decorator(func: Callable[..., Awaitable[TaskResult]]) -> Callable[..., Awaitable[object]]:
        @wraps(func)
        async def wrapper(agent_url: str, *args: object, **kwargs: object) -> object:
            """
            Execute the wrapped task builder and call the target agent.

            Args:
                agent_url: URL of the Strands agent endpoint.
                *args: Positional args for the wrapped function.
                **kwargs: Keyword args for the wrapped function.

            Returns:
                Raw agent response from `StrandsAgentClient.call_agent`.
            """
            logger.info("Starting Strands agent activity")

            # Get required capabilities from function metadata (set by config loader)
            required_capabilities_obj = getattr(wrapper, "_required_capabilities", None)
            required_capabilities: list[str] | None = (
                cast(list[str], required_capabilities_obj) if isinstance(required_capabilities_obj, list) else None
            )

            # Call the user's function to get task parameters
            task_params = await func(*args, **kwargs)

            # Execute agent call using shared logic
            return await _execute_agent_call(
                agent_url=agent_url,
                task_params=task_params,
                timeout_seconds=timeout_seconds,
                heartbeat_timeout_seconds=heartbeat_timeout_seconds,
                check_capabilities=check_capabilities,
                required_capabilities=required_capabilities,
                validate_response=validate_response,
                wrapper_func=wrapper,
            )

        # Apply Temporal activity decorator
        activity_decorator = activity.defn(name=name or func.__name__)
        decorated_wrapper = activity_decorator(wrapper)

        return decorated_wrapper

    return decorator


def _validate_agent_response(result: object, agent_url: str) -> None:
    """
    Validate structured agent responses and raise Temporal errors on failure.

    Args:
        result: Agent response to validate
        agent_url: Agent URL for error context

    Raises:
        ApplicationError: For structured failed responses (`status == "failed"`).
    """
    # Check if result is a dict (expected structured response)
    if not isinstance(result, dict):
        logger.warning(f"Agent {agent_url} returned non-dict response: {type(result)}")
        return  # Allow non-structured responses for backward compatibility

    result_map = cast(dict[str, object], result)
    status_obj = result_map.get("status")

    # Real A2A Task responses nest state in status.state, e.g. {"state": "failed", ...}
    if isinstance(status_obj, dict):
        _validate_task_status(cast(dict[str, object], status_obj), agent_url)
        return

    status = status_obj if isinstance(status_obj, str) else None

    # Check for explicit failure status
    if status == "failed":
        error_obj = result_map.get("error", "Unknown error")
        error_msg = error_obj if isinstance(error_obj, str) else "Unknown error"
        retry_obj = result_map.get("retry_suggestion", "")
        retry_suggestion = retry_obj if isinstance(retry_obj, str) else ""

        # Determine if error should be retryable
        retryable = _should_retry_error(error_msg)

        full_error = f"Agent task failed: {error_msg}"
        if retry_suggestion:
            full_error += f" (Suggestion: {retry_suggestion})"

        logger.error(f"Agent {agent_url} failed: {full_error}")

        raise ApplicationError(full_error, non_retryable=not retryable, type="AgentTaskFailure")

    # Check for missing status (potential protocol violation)
    if status is not None and status not in ["completed", "failed"]:
        logger.warning(f"Agent {agent_url} returned unexpected status: {status}")
        # Don't fail for unknown status, just log warning

    # Log successful completion
    if status == "completed":
        summary_obj = result_map.get("summary", "No summary")
        summary = summary_obj if isinstance(summary_obj, str) else "No summary"
        logger.info(f"Agent {agent_url} completed successfully: {summary}")


_A2A_FAILURE_STATES = {"failed", "rejected", "canceled"}
_A2A_ATTENTION_STATES = {"input-required", "auth-required"}


def _validate_task_status(status_obj: dict[str, object], agent_url: str) -> None:
    """
    Validate a dict-shaped A2A Task status, e.g. {"state": "failed", "message": "..."}.

    Raises:
        ApplicationError: For failed/rejected/canceled states (non-retryable), or
            input-required/auth-required states (needs external action, non-retryable).
    """
    state_obj = status_obj.get("state")
    state = state_obj if isinstance(state_obj, str) else None

    message = _extract_status_message(status_obj.get("message"))

    if state in _A2A_FAILURE_STATES:
        full_error = f"Agent task {state}: {message}" if message else f"Agent task {state}"
        logger.error(f"Agent {agent_url} task {state}: {full_error}")
        raise ApplicationError(full_error, non_retryable=True, type="AgentTaskFailure")

    if state in _A2A_ATTENTION_STATES:
        full_error = f"Agent task requires {state}: {message}" if message else f"Agent task requires {state}"
        logger.warning(f"Agent {agent_url} task requires attention ({state}): {full_error}")
        raise ApplicationError(full_error, non_retryable=True, type="AgentTaskAttentionRequired")

    if state is not None and state not in {"completed", "working", "submitted"}:
        logger.warning(f"Agent {agent_url} returned unexpected task state: {state}")


def _extract_status_message(message_obj: object) -> str | None:
    """
    Read the human-readable text from an A2A TaskStatus message.

    The A2A spec makes `status.message` a Message object whose text lives in
    `parts`, e.g. {"role": "agent", "parts": [{"kind": "text", "text": "..."}]}.
    A plain string is also accepted.
    """
    if isinstance(message_obj, str):
        return message_obj or None
    if not isinstance(message_obj, dict):
        return None

    parts_obj = cast(dict[str, object], message_obj).get("parts")
    if not isinstance(parts_obj, list):
        return None

    texts: list[str] = []
    for part in cast(list[object], parts_obj):
        if isinstance(part, dict):
            text = cast(dict[str, object], part).get("text")
            if isinstance(text, str) and text:
                texts.append(text)
    return " ".join(texts) or None


def _should_retry_error(error_msg: str | None) -> bool:
    """
    Heuristic to classify an error message as retryable or non-retryable.

    Args:
        error_msg: Error message from agent

    Returns:
        True if error seems retryable (transient), False if permanent
    """
    if not error_msg:
        return False

    error_lower = error_msg.lower()

    # Retryable errors (transient issues)
    retryable_keywords = [
        "timeout",
        "connection",
        "network",
        "temporary",
        "rate limit",
        "service unavailable",
        "server error",
        "busy",
        "overloaded",
    ]

    # Non-retryable errors (permanent issues)
    non_retryable_keywords = [
        "invalid input",
        "bad request",
        "unauthorized",
        "forbidden",
        "not found",
        "permission denied",
        "invalid format",
        "parse error",
    ]

    # Check non-retryable first (more specific)
    for keyword in non_retryable_keywords:
        if keyword in error_lower:
            return False

    # Check retryable
    for keyword in retryable_keywords:
        if keyword in error_lower:
            return True

    # Default to retryable for unknown errors
    return True


# Core activity for general Strands agent calls


@strands_agent_activity(name="call_strands_agent", timeout_seconds=300, heartbeat_timeout_seconds=60)
async def call_strands_agent(
    task: str, query_extra_data: dict[str, object] | None = None, session_id: str | None = None, **kwargs: object
) -> dict[str, object]:
    """
    Default generic activity for calling any Strands agent.

    Args:
        task: Task text sent to the agent.
        query_extra_data: Optional context payload included in the message body.
        session_id: Optional conversation/session identifier.
        **kwargs: Additional values forwarded into the agent request payload.

    Returns:
        A task payload consumed by the decorator wrapper.
    """
    return {
        "task": task,
        "context": query_extra_data or {},  # Keep internal key for compatibility
        "session_id": session_id,
        **kwargs,
    }


def strands_agent_dataclass_activity(
    name: str | None = None,
    timeout_seconds: int = 300,
    heartbeat_timeout_seconds: int | None = None,
    check_capabilities: list[str] | None = None,
    validate_response: bool = False,
):
    """
    Decorator for activities that accept a single dataclass input parameter.

    This decorator follows Temporal best practices by encouraging a single
    dataclass parameter instead of multiple parameters, making activity
    interfaces easier to evolve over time.

    Note: This decorator does not support output dataclasses. Agent responses
    are text-based, so there is no need for structured output dataclass conversion.
    Users can wrap or parse the text response in their workflow code if needed.

    Args:
        name: Temporal activity name. Defaults to the function name.
        timeout_seconds: HTTP timeout (seconds) used by `StrandsAgentClient`.
        heartbeat_timeout_seconds: If set, enables periodic activity heartbeats.
            Heartbeats are sent every `max(1, heartbeat_timeout_seconds // 4)`.
        check_capabilities: Optional required capabilities to validate before calling.
        validate_response: If True, validates structured agent failure responses.

    Returns:
        Temporal activity function that accepts a single dataclass input parameter,
        then forwards the wrapped function's result to the Strands agent.
        The activity returns the raw agent response (typically text).

    Example:
        from foundry_temporal_agents.models import StrandsAgentTaskInput

        @strands_agent_dataclass_activity(name="process_task")
        async def process_task_activity(input_data: StrandsAgentTaskInput) -> dict:
            # input_data is a dataclass with task, query_extra_data, session_id, etc.
            return {
                "task": input_data.task,
                "context": input_data.query_extra_data,
            }
    """

    def decorator(func: Callable[..., Awaitable[TaskResult]]) -> Callable[..., Awaitable[object]]:
        _input_type = _resolve_first_param_type(func)

        @wraps(func)
        async def wrapper(agent_url: str, input_data: Any) -> object:
            """
            Execute the wrapped task builder and call the target agent.

            Args:
                agent_url: URL of the Strands agent endpoint.
                input_data: Dataclass input containing activity parameters.

            Returns:
                Raw agent response from `StrandsAgentClient.call_agent`.
            """
            logger.info("Starting Strands agent activity with dataclass input")

            # Get required capabilities from function metadata (set by config loader)
            required_capabilities_obj = getattr(wrapper, "_required_capabilities", None)
            required_capabilities: list[str] | None = (
                cast(list[str], required_capabilities_obj) if isinstance(required_capabilities_obj, list) else None
            )

            resolved = _coerce_input(input_data, _input_type)

            # Call the user's function to get task parameters
            task_params = await func(resolved)

            # Execute agent call using shared logic
            return await _execute_agent_call(
                agent_url=agent_url,
                task_params=task_params,
                timeout_seconds=timeout_seconds,
                heartbeat_timeout_seconds=heartbeat_timeout_seconds,
                check_capabilities=check_capabilities,
                required_capabilities=required_capabilities,
                validate_response=validate_response,
                wrapper_func=wrapper,
            )

        # Apply Temporal activity decorator
        activity_decorator = activity.defn(name=name or func.__name__)
        decorated_wrapper = activity_decorator(wrapper)

        return decorated_wrapper

    return decorator


@strands_agent_dataclass_activity(
    name="call_strands_agent_dataclass", timeout_seconds=300, heartbeat_timeout_seconds=60
)
async def call_strands_agent_dataclass(input_data: StrandsAgentTaskInput) -> dict[str, object]:
    """
    Dataclass-based version of call_strands_agent following Temporal best practices.

    This activity accepts a single StrandsAgentTaskInput dataclass parameter,
    making it easier to evolve the interface over time and providing better
    type safety and IDE support.

    Args:
        input_data: StrandsAgentTaskInput dataclass containing:
            - task: Task text sent to the agent
            - query_extra_data: Optional context payload
            - session_id: Optional conversation/session identifier
            - additional_params: Additional parameters forwarded to the agent

    Returns:
        A task payload consumed by the decorator wrapper.

    Example:
        from foundry_temporal_agents import call_strands_agent_dataclass, StrandsAgentTaskInput

        # In workflow:
        input_data = StrandsAgentTaskInput(
            task="Analyze this document",
            query_extra_data={"file": "document.pdf"},
            session_id="session-123"
        )
        result = await execute_activity(
            call_strands_agent_dataclass,
            args=[agent_url, input_data],
            start_to_close_timeout=timedelta(minutes=5)
        )
    """
    return {
        "task": input_data.task,
        "context": input_data.query_extra_data or {},  # Keep internal key for compatibility
        "session_id": input_data.session_id,
        **input_data.additional_params,
    }
