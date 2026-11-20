# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Temporal activity helpers for Strands Query API calls."""

import asyncio
import inspect
import logging
import os
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, cast, get_type_hints

from foundry_temporal import get_header
from temporalio import activity
from temporalio.exceptions import ApplicationError

from .exceptions import QueryProcessingError
from .query_client import StrandsQueryClient
from .query_models import StrandsQueryTaskInput
from .tls import create_agent_tls_context

logger = logging.getLogger(__name__)

type QueryResult = dict[str, object]

# Bearer credential the agent's auth middleware validates. See
# FOUNDRY_TLS_MODE in tls.py for the equivalent env-var-driven pattern.
_BEARER_TOKEN_ENV_VAR = "FOUNDRY_AGENT_BEARER_TOKEN"

# Back-compat alias: the original query-only variable name. Checked when
# the primary variable above is unset, so existing query-only deployments
# don't need a config change. Deprecated: using it logs a warning, and a
# future major version will remove it.
_BEARER_TOKEN_ENV_VAR_ALIAS = "FOUNDRY_AGENT_QUERY_BEARER_TOKEN"

# Forwarded as-is for backward compatibility with agent deployments that
# still read it. It is not an `Authorization: <scheme> <credentials>` header
# per RFC 7235 and is never treated as validated here - the bearer token
# above is the sole authentication signal.
_IDENTITY_HEADER = "x-identity-token"


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
    if hasattr(expected_type, "model_validate"):
        return expected_type.model_validate(input_data)
    return expected_type(**input_data)


async def _execute_query_call(
    agent_url: str,
    task_params: QueryResult,
    timeout_seconds: int,
    heartbeat_timeout_seconds: int | None,
    validate_response: bool,
    wrapper_func: Callable,
) -> object:
    """
    Shared logic for executing Strands query API calls.

    This extracts the common query calling logic used by both
    strands_query_activity and strands_query_dataclass_activity.

    Args:
        agent_url: URL of the Strands agent endpoint
        task_params: Query parameters from the wrapped function
        timeout_seconds: HTTP timeout
        heartbeat_timeout_seconds: Heartbeat configuration
        validate_response: Whether to validate response
        wrapper_func: The wrapper function (for accessing metadata)

    Returns:
        Raw query response from StrandsQueryClient.query_agent
    """
    # Extract query and parameters from function result
    if isinstance(task_params, dict):
        query = str(task_params.get("query", ""))
        context_obj = task_params.get("context", {})
        context = cast(dict[str, object], context_obj) if isinstance(context_obj, dict) else {}

        session_id_obj = task_params.get("session_id")
        session_id = session_id_obj if isinstance(session_id_obj, str) else None

        max_results_obj = task_params.get("max_results", 10)
        max_results = int(max_results_obj) if isinstance(max_results_obj, (int, float)) else 10

        threshold_obj = task_params.get("similarity_threshold", 0.7)
        similarity_threshold = float(threshold_obj) if isinstance(threshold_obj, (int, float)) else 0.7

        additional_params = {
            k: v
            for k, v in task_params.items()
            if k not in ["query", "context", "session_id", "max_results", "similarity_threshold"]
        }
    else:
        raise ValueError("Query activity function must return dict")

    # Set up continuous heartbeat if configured
    heartbeat_task = None
    if heartbeat_timeout_seconds:

        async def periodic_heartbeat():
            assert heartbeat_timeout_seconds is not None
            heartbeat_interval = max(1, heartbeat_timeout_seconds // 4)
            while True:
                await asyncio.sleep(heartbeat_interval)
                activity.heartbeat(f"Query call in progress: {agent_url}")

        heartbeat_task = asyncio.create_task(periodic_heartbeat())
        activity.heartbeat(f"Starting query call: {agent_url}")

    # Attach the bearer credential the agent's auth middleware validates.
    auth_headers: dict[str, str] = {}
    if bearer_token := os.getenv(_BEARER_TOKEN_ENV_VAR):
        auth_headers = {"Authorization": f"Bearer {bearer_token}"}
    elif bearer_token := os.getenv(_BEARER_TOKEN_ENV_VAR_ALIAS):
        logger.warning(
            "%s is deprecated and will be removed in a future major version; set %s instead.",
            _BEARER_TOKEN_ENV_VAR_ALIAS,
            _BEARER_TOKEN_ENV_VAR,
        )
        auth_headers = {"Authorization": f"Bearer {bearer_token}"}
    else:
        logger.warning(
            "Neither %s nor %s is set; sending unauthenticated query request to %s. "
            "This will become a hard failure in an upcoming release - "
            "set the credential now to avoid disruption.",
            _BEARER_TOKEN_ENV_VAR,
            _BEARER_TOKEN_ENV_VAR_ALIAS,
            agent_url,
        )

    # Forward the propagated identity token, if any, for backward
    # compatibility with agent deployments that still read it. It is never
    # treated as an authentication signal - the bearer token above is.
    if identity_token := get_header(_IDENTITY_HEADER):
        auth_headers[_IDENTITY_HEADER] = identity_token

    try:
        # Call the Strands query API. max_retries=0 is deliberate: this is always
        # invoked from inside a Temporal activity, so the Temporal activity retry
        # policy is the sole retry authority. An inner retry loop here would
        # compound with Temporal's own retries.
        ssl_context = create_agent_tls_context()
        async with StrandsQueryClient(
            agent_url=agent_url,
            timeout=timeout_seconds,
            max_retries=0,
            auth_headers=auth_headers,
            ssl_context=ssl_context,
        ) as client:
            try:
                result = await client.query_agent(
                    query=query,
                    context=context,
                    session_id=session_id,
                    max_results=max_results,
                    similarity_threshold=similarity_threshold,
                    **additional_params,
                )
            except QueryProcessingError as e:
                if not e.retryable:
                    raise ApplicationError(str(e), non_retryable=True) from e
                raise

            # Validate query response if enabled
            if validate_response:
                _validate_query_response(result, agent_url)

            # Send final heartbeat
            if heartbeat_timeout_seconds:
                activity.heartbeat("Query call completed successfully")

            logger.info("Strands query activity completed")
            return result

    finally:
        # Stop heartbeat task
        if heartbeat_task:
            _ = heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass


def strands_query_activity(
    name: str | None = None,
    timeout_seconds: int = 300,
    heartbeat_timeout_seconds: int | None = None,
    validate_response: bool = False,
):
    """
    Decorate an async function that builds a query payload for a Strands agent.

    This decorator is similar to strands_agent_activity but targets the query API
    endpoint (/api/v1/query) instead of the A2A JSON-RPC protocol. It provides
    access to structured query responses with search results and confidence scores.

    Args:
        name: Temporal activity name. Defaults to the function name.
        timeout_seconds: HTTP timeout (seconds) used by `StrandsQueryClient`.
        heartbeat_timeout_seconds: If set, enables periodic activity heartbeats.
            Heartbeats are sent every `max(1, heartbeat_timeout_seconds // 4)`.
        validate_response: If True, validates structured query responses.

    Returns:
        Temporal activity function that accepts `agent_url` as the first arg,
        then forwards the remaining args/kwargs to the wrapped function.
    """

    def decorator(func: Callable[..., Awaitable[QueryResult]]) -> Callable[..., Awaitable[object]]:
        @wraps(func)
        async def wrapper(agent_url: str, *args: object, **kwargs: object) -> object:
            """
            Execute the wrapped query builder and call the target agent.

            Args:
                agent_url: URL of the Strands agent endpoint.
                *args: Positional args for the wrapped function.
                **kwargs: Keyword args for the wrapped function.

            Returns:
                Raw query response from `StrandsQueryClient.query_agent`.
            """
            logger.info("Starting Strands query activity")

            # Call the user's function to get query parameters
            task_params = await func(*args, **kwargs)

            # Execute query call using shared logic
            return await _execute_query_call(
                agent_url=agent_url,
                task_params=task_params,
                timeout_seconds=timeout_seconds,
                heartbeat_timeout_seconds=heartbeat_timeout_seconds,
                validate_response=validate_response,
                wrapper_func=wrapper,
            )

        # Apply Temporal activity decorator
        activity_decorator = activity.defn(name=name or func.__name__)
        decorated_wrapper = activity_decorator(wrapper)

        return decorated_wrapper

    return decorator


def _validate_query_response(result: object, agent_url: str) -> None:
    """
    Validate structured query responses and raise Temporal errors on failure.

    Args:
        result: Query response to validate
        agent_url: Agent URL for error context

    Raises:
        ApplicationError: For malformed or failed responses.
    """
    # Check if result is a dict (expected structured response)
    if not isinstance(result, dict):
        logger.warning(f"Agent {agent_url} returned non-dict response: {type(result)}")
        return  # Allow non-structured responses for backward compatibility

    result_map = cast(dict[str, object], result)

    # Check for expected query response fields
    expected_fields = ["response_text", "confidence_score"]
    missing_fields = [field for field in expected_fields if field not in result_map]

    if missing_fields:
        logger.warning(f"Query response missing expected fields {missing_fields} from {agent_url}")
        # Don't fail for missing fields, just log warning for backward compatibility

    # Check for error indicators in response
    confidence_obj = result_map.get("confidence_score")
    if isinstance(confidence_obj, (int, float)):
        confidence = float(confidence_obj)
        if confidence < 0.1:  # Very low confidence might indicate an issue
            logger.warning(f"Query response has very low confidence ({confidence}) from {agent_url}")

    # Log successful completion with response info
    response_text_obj = result_map.get("response_text", "")
    response_text = response_text_obj if isinstance(response_text_obj, str) else ""
    processing_time_obj = result_map.get("processing_time_ms", 0)
    processing_time = processing_time_obj if isinstance(processing_time_obj, (int, float)) else 0

    logger.info(f"Query completed successfully from {agent_url}: {len(response_text)} chars, {processing_time}ms")


def strands_query_dataclass_activity(
    name: str | None = None,
    timeout_seconds: int = 300,
    heartbeat_timeout_seconds: int | None = None,
    validate_response: bool = False,
):
    """
    Decorator for query activities that accept a single dataclass input parameter.

    This decorator follows Temporal best practices by encouraging a single
    dataclass parameter instead of multiple parameters, making activity
    interfaces easier to evolve over time.

    Args:
        name: Temporal activity name. Defaults to the function name.
        timeout_seconds: HTTP timeout (seconds) used by `StrandsQueryClient`.
        heartbeat_timeout_seconds: If set, enables periodic activity heartbeats.
            Heartbeats are sent every `max(1, heartbeat_timeout_seconds // 4)`.
        validate_response: If True, validates structured query responses.

    Returns:
        Temporal activity function that accepts a single dataclass input parameter,
        then forwards the wrapped function's result to the Strands query API.

    Example:
        from foundry_strands_agents.query_models import StrandsQueryTaskInput

        @strands_query_dataclass_activity(name="search_documents")
        async def search_documents_activity(input_data: StrandsQueryTaskInput) -> dict:
            return {
                "query": input_data.query,
                "context": input_data.context,
                "max_results": input_data.max_results,
            }
    """

    def decorator(func: Callable[..., Awaitable[QueryResult]]) -> Callable[..., Awaitable[object]]:
        _input_type = _resolve_first_param_type(func)

        @wraps(func)
        async def wrapper(agent_url: str, input_data: Any) -> object:
            """
            Execute the wrapped query builder and call the target agent.

            Args:
                agent_url: URL of the Strands agent endpoint.
                input_data: Dataclass input containing query parameters.

            Returns:
                Raw query response from `StrandsQueryClient.query_agent`.
            """
            logger.info("Starting Strands query activity with dataclass input")

            resolved = _coerce_input(input_data, _input_type)

            # Call the user's function to get query parameters
            task_params = await func(resolved)

            # Execute query call using shared logic
            return await _execute_query_call(
                agent_url=agent_url,
                task_params=task_params,
                timeout_seconds=timeout_seconds,
                heartbeat_timeout_seconds=heartbeat_timeout_seconds,
                validate_response=validate_response,
                wrapper_func=wrapper,
            )

        # Apply Temporal activity decorator
        activity_decorator = activity.defn(name=name or func.__name__)
        decorated_wrapper = activity_decorator(wrapper)

        return decorated_wrapper

    return decorator


# Core activities for general Strands query API calls


@strands_query_activity(name="call_strands_query", timeout_seconds=300, heartbeat_timeout_seconds=60)
async def call_strands_query(
    query: str,
    context: dict[str, object] | None = None,
    session_id: str | None = None,
    max_results: int = 10,
    similarity_threshold: float = 0.7,
    **kwargs: object,
) -> dict[str, object]:
    """
    Default generic activity for calling any Strands query API.

    Args:
        query: The user's question or query to be processed.
        context: Optional context information to help with query processing.
        session_id: Optional session identifier for conversation continuity.
        max_results: Maximum number of results to return (1-100).
        similarity_threshold: Minimum similarity threshold (0.0-1.0).
        **kwargs: Additional values forwarded into the query request payload.

    Returns:
        A query payload consumed by the decorator wrapper.
    """
    return {
        "query": query,
        "context": context or {},
        "session_id": session_id,
        "max_results": max_results,
        "similarity_threshold": similarity_threshold,
        **kwargs,
    }


@strands_query_dataclass_activity(
    name="call_strands_query_dataclass", timeout_seconds=300, heartbeat_timeout_seconds=60
)
async def call_strands_query_dataclass(input_data: StrandsQueryTaskInput) -> dict[str, object]:
    """
    Dataclass-based version of call_strands_query following Temporal best practices.

    This activity accepts a single StrandsQueryTaskInput dataclass parameter,
    making it easier to evolve the interface over time and providing better
    type safety and IDE support.

    Args:
        input_data: StrandsQueryTaskInput dataclass containing:
            - query: The user's question or query
            - context: Optional context information
            - session_id: Optional session identifier
            - max_results: Maximum number of results
            - similarity_threshold: Minimum similarity threshold
            - additional_params: Additional parameters forwarded to the API

    Returns:
        A query payload consumed by the decorator wrapper.

    Example:
        from foundry_strands_agents import call_strands_query_dataclass, StrandsQueryTaskInput

        # In workflow:
        input_data = StrandsQueryTaskInput(
            query="What are the main architectural patterns?",
            context={"source": "documentation"},
            session_id="session-123",
            max_results=15,
            similarity_threshold=0.8
        )
        result = await execute_activity(
            call_strands_query_dataclass,
            args=[agent_url, input_data],
            start_to_close_timeout=timedelta(minutes=5)
        )
    """
    return {
        "query": input_data.query,
        "context": input_data.context or {},
        "session_id": input_data.session_id,
        "max_results": input_data.max_results,
        "similarity_threshold": input_data.similarity_threshold,
        **input_data.additional_params,
    }
