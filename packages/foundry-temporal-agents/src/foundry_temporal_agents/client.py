# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Async HTTP client for Strands A2A protocol communication."""

import asyncio
import logging
import ssl
from types import TracebackType
from typing import cast

import aiohttp

from .exceptions import (
    A2AProtocolError,
    AgentAuthenticationError,
    AgentNotFoundError,
    AgentRequestError,
    AgentTimeoutError,
    AgentUnavailableError,
)
from .protocols import A2AMessageBuilder, extract_agent_response, validate_a2a_response
from .retry import is_non_retryable_http_status

logger = logging.getLogger(__name__)


class StrandsAgentClient:
    """
    Async client for sending A2A JSON-RPC requests to a Strands agent.
    """

    def __init__(
        self,
        agent_url: str,
        timeout: int = 300,
        max_retries: int = 3,
        session: aiohttp.ClientSession | None = None,
        ssl_context: ssl.SSLContext | None = None,
        auth_headers: dict[str, str] | None = None,
    ):
        """
        Initialize the client.

        Args:
            agent_url: Base URL of the Strands agent endpoint.
            timeout: Request timeout in seconds.
            max_retries: Number of retries after the first attempt.
            session: Optional shared aiohttp session.
            ssl_context: Optional SSL context for TLS/mTLS connections.
            auth_headers: Optional headers (e.g. a bearer credential) attached
                to every outbound request. Caller is responsible for sourcing
                the values. Placed after `ssl_context` so positional calls
                written against 0.2.0 keep working.
        """
        self.agent_url: str = agent_url.rstrip("/")
        self.timeout: int = timeout
        self.max_retries: int = max_retries
        self._ssl_context: ssl.SSLContext | None = ssl_context
        self._session: aiohttp.ClientSession | None = session
        self._owns_session: bool = session is None
        self.auth_headers: dict[str, str] = auth_headers or {}
        self._message_builder: A2AMessageBuilder = A2AMessageBuilder()

    def _create_session(self) -> aiohttp.ClientSession:
        """Create an aiohttp session, optionally with a TLS connector."""
        if self._ssl_context:
            connector = aiohttp.TCPConnector(ssl=self._ssl_context)
            return aiohttp.ClientSession(connector=connector)
        return aiohttp.ClientSession()

    async def __aenter__(self) -> StrandsAgentClient:
        """Async context manager entry"""
        if self._session is None:
            self._session = self._create_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit"""
        if self._owns_session and self._session:
            await self._session.close()

    async def _ensure_session(self):
        """Ensure we have an HTTP session"""
        if self._session is None:
            self._session = self._create_session()

    async def call_agent(
        self,
        task: str,
        query_extra_data: dict[str, object] | None = None,
        **kwargs: object,
    ) -> object:
        """
        Send a task to the agent and return the extracted response payload.

        Args:
            task: Task description.
            query_extra_data: Optional extra data appended to the task message.
            **kwargs: Additional values included in the A2A message.
                If `session_id` is provided, it will be used as the A2A sessionId.

        Returns:
            Agent response

        Raises:
            AgentNotFoundError: Agent returned 404, or is unreachable or kept
                returning 408/429/5xx after retries (`status` holds the HTTP code).
            AgentAuthenticationError: Agent rejected the request as
                unauthenticated/unauthorized (401/403).
            AgentTimeoutError: Request exceeded timeout.
            A2AProtocolError: Response is not valid A2A JSON-RPC shape.
            AgentRequestError: Agent rejected the request with a non-retryable
                4xx status.
        """
        await self._ensure_session()
        assert self._session is not None  # Guaranteed by _ensure_session

        session_id_obj = kwargs.pop("session_id", None)
        session_id = session_id_obj if isinstance(session_id_obj, str) else None

        # Build message
        message_kwargs = dict(kwargs)
        # Preserve historical behavior: session_id is also included in message parameters,
        # even when session_id is None.
        message_kwargs["session_id"] = session_id
        message = self._message_builder.create_task_message(task, query_extra_data, **message_kwargs)
        request_data = self._message_builder.create_request(message, method="message/send", session_id=session_id)

        logger.info(f"Calling agent: {self.agent_url}")

        # Execute request with retries
        last_exception: Exception | None = None
        for attempt in range(int(self.max_retries) + 1):
            try:
                async with self._session.post(
                    self.agent_url,
                    json=request_data,
                    headers=self.auth_headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status == 404:
                        raise AgentNotFoundError(self.agent_url, status=404)

                    if response.status in (401, 403):
                        raise AgentAuthenticationError(self.agent_url, response.status)

                    response.raise_for_status()
                    response_data_obj = cast(object, await response.json())
                    if not isinstance(response_data_obj, dict):
                        raise A2AProtocolError(
                            "Invalid A2A response format",
                            {"raw_response_type": str(type(response_data_obj))},
                        )
                    response_data = cast(dict[str, object], response_data_obj)

                    # Validate A2A protocol response
                    if not validate_a2a_response(response_data):
                        raise A2AProtocolError("Invalid A2A response format", response_data)

                    # Extract and return agent response
                    agent_response = extract_agent_response(response_data)
                    logger.info(f"Agent call successful (attempt {attempt + 1})")
                    return agent_response

            except AgentAuthenticationError:
                # Not retryable: the credential is wrong/missing, retrying won't help.
                logger.error(f"Agent authentication failed for {self.agent_url}")
                raise

            except AgentNotFoundError:
                # Not retryable: the endpoint returned 404, retrying won't help.
                logger.error(f"Agent endpoint not found: {self.agent_url}")
                raise

            except TimeoutError as e:
                last_exception = AgentTimeoutError(self.agent_url, self.timeout)
                logger.warning(f"Agent timeout on attempt {attempt + 1}: {e}")

            except aiohttp.ClientResponseError as e:
                if is_non_retryable_http_status(e.status):
                    # Client error (bad request, auth failure, etc.) — retrying
                    # won't help, so fail fast without consuming the retry budget.
                    logger.error(f"Non-retryable client error from {self.agent_url}: HTTP {e.status}")
                    raise AgentRequestError(self.agent_url, e.status, e) from e
                if e.status < 400:
                    # A status below 400 whose body isn't JSON (ContentTypeError): a gateway's HTML
                    # page while the agent warms up, an unfollowed 3xx, or too many redirects.
                    # Retried like the other A2AProtocolError paths.
                    protocol_error = A2AProtocolError(f"Invalid response format from agent: {e}")
                    protocol_error.__cause__ = e
                    last_exception = protocol_error
                    logger.warning(
                        f"Agent protocol error on attempt {attempt + 1}: HTTP {e.status} with a non-JSON body"
                    )
                else:
                    # Only 408, 429 and 5xx reach here; the permanent statuses were handled above.
                    last_exception = AgentUnavailableError(self.agent_url, e, status=e.status)
                    logger.warning(f"Agent server error on attempt {attempt + 1}: HTTP {e.status}: {e}")

            except aiohttp.ClientError as e:
                last_exception = AgentNotFoundError(self.agent_url, e)
                logger.warning(f"Agent connection error on attempt {attempt + 1}: {e}")

            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")

            # Wait before retry (except on last attempt)
            if attempt < self.max_retries:
                attempt_index: int = attempt
                wait_time = 2**attempt_index  # Exponential backoff
                logger.info(f"Retrying in {wait_time}s...")
                await asyncio.sleep(float(wait_time))

        # All retries exhausted
        logger.error(f"Agent call failed after {self.max_retries + 1} attempts")
        raise last_exception or AgentNotFoundError(self.agent_url)

    async def discover_capabilities(self) -> dict[str, object]:
        """
        Fetch agent capabilities from `/.well-known/agent-card.json`.

        Returns:
            Agent card payload.

        Raises:
            AgentNotFoundError: Agent card cannot be retrieved.
        """
        await self._ensure_session()
        assert self._session is not None  # Guaranteed by _ensure_session

        agent_card_url = f"{self.agent_url}/.well-known/agent-card.json"

        try:
            async with self._session.get(agent_card_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                agent_card_obj = cast(object, await response.json())
                if not isinstance(agent_card_obj, dict):
                    raise AgentNotFoundError(self.agent_url)
                agent_card = cast(dict[str, object], agent_card_obj)
                agent_name_obj = agent_card.get("name", "unknown")
                agent_name = agent_name_obj if isinstance(agent_name_obj, str) else "unknown"
                logger.info(f"Agent capabilities discovered: {agent_name}")
                return agent_card

        except Exception as e:
            raise AgentNotFoundError(self.agent_url, e) from e

    async def health_check(self) -> bool:
        """
        Check whether the agent health endpoint returns a 2xx status.

        Returns:
            True if agent is healthy
        """
        await self._ensure_session()
        assert self._session is not None  # Guaranteed by _ensure_session

        health_url = f"{self.agent_url}/health"

        try:
            # Shorter timeout for health checks
            async with self._session.get(health_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                # Accept both 200 and other 2xx status codes as healthy
                return 200 <= response.status < 300

        except Exception as e:
            logger.debug(f"Health check failed for {self.agent_url}: {e}")
            return False

    async def close(self):
        """Close the HTTP session"""
        if self._owns_session and self._session:
            await self._session.close()
