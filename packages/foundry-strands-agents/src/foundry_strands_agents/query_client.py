# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Async HTTP client for Strands Query API communication."""

import asyncio
import json
import logging
import ssl
from collections.abc import AsyncGenerator
from types import TracebackType

import aiohttp

from .exceptions import AgentNotFoundError, AgentTimeoutError, QueryProcessingError

_NON_RETRYABLE_STATUSES = frozenset(range(400, 500))

logger = logging.getLogger(__name__)


class StrandsQueryClient:
    """
    Async client for sending HTTP requests to Strands Query API.

    This client interfaces with the REST query endpoint (/api/v1/query) rather than
    the A2A JSON-RPC protocol, providing access to structured query responses with
    search results, document chunks, and confidence scoring.
    """

    def __init__(
        self,
        agent_url: str,
        timeout: int = 300,
        max_retries: int = 3,
        session: aiohttp.ClientSession | None = None,
        auth_headers: dict[str, str] | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ):
        """
        Initialize the query client.

        Args:
            agent_url: Base URL of the Strands agent endpoint.
            timeout: Request timeout in seconds.
            max_retries: Number of retries after the first attempt.
            session: Optional shared aiohttp session.
            auth_headers: Optional headers (e.g. identity/auth tokens) attached
                to every outbound request. Caller is responsible for sourcing
                the values (e.g. from Temporal activity context headers).
            ssl_context: Optional SSL context for TLS/mTLS connections.
        """
        self.agent_url: str = agent_url.rstrip("/")
        self.timeout: int = timeout
        self.max_retries: int = max_retries
        self._ssl_context: ssl.SSLContext | None = ssl_context
        self._session: aiohttp.ClientSession | None = session
        self._owns_session: bool = session is None
        self.auth_headers: dict[str, str] = auth_headers or {}

    def _create_session(self) -> aiohttp.ClientSession:
        """Create an aiohttp session, optionally with a TLS connector."""
        if self._ssl_context:
            connector = aiohttp.TCPConnector(ssl=self._ssl_context)
            return aiohttp.ClientSession(connector=connector)
        return aiohttp.ClientSession()

    async def __aenter__(self) -> StrandsQueryClient:
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

    async def query_agent(
        self,
        query: str,
        context: dict[str, object] | None = None,
        session_id: str | None = None,
        max_results: int = 10,
        similarity_threshold: float = 0.7,
        **kwargs: object,
    ) -> dict[str, object]:
        """
        Send a query to the agent's query API endpoint.

        Args:
            query: The user's question or query to be processed.
            context: Optional context information to help with query processing.
            session_id: Optional session identifier for conversation continuity.
            max_results: Maximum number of results to return (1-100).
            similarity_threshold: Minimum similarity threshold (0.0-1.0).
            **kwargs: Additional parameters forwarded to the API.

        Returns:
            Query response dictionary with structured results including:
            - response_text: The agent's generated response
            - sources: List of search results that informed the response
            - chunks_used: Specific content chunks used
            - confidence_score: Confidence level (0.0-1.0)
            - processing_time_ms: Processing time in milliseconds

        Raises:
            AgentNotFoundError: Agent is unreachable / endpoint not found.
            AgentTimeoutError: Request exceeded timeout.
            QueryProcessingError: Query processing failed.
        """
        await self._ensure_session()
        assert self._session is not None

        # Build request payload matching QueryAPIRequest structure
        request_data = {
            "query": query,
            "max_results": max_results,
            "similarity_threshold": similarity_threshold,
        }

        if context is not None:
            request_data["context"] = context
        if session_id is not None:
            request_data["session_id"] = session_id

        # Add any additional kwargs
        request_data.update(kwargs)

        query_url = f"{self.agent_url}/api/v1/query"
        logger.info(f"Querying agent: {query_url}")

        # Execute request with retries
        last_exception: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with self._session.post(
                    query_url,
                    json=request_data,
                    headers=self.auth_headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    if response.status == 404:
                        raise AgentNotFoundError(self.agent_url)

                    response.raise_for_status()
                    response_data_obj = await response.json()

                    if not isinstance(response_data_obj, dict):
                        raise QueryProcessingError(
                            f"Invalid query response format from {self.agent_url}",
                            {"response_type": str(type(response_data_obj))},
                        )

                    response_data = dict(response_data_obj)
                    logger.info(f"Query successful (attempt {attempt + 1})")
                    return response_data

            except TimeoutError as e:
                last_exception = AgentTimeoutError(self.agent_url, self.timeout)
                logger.warning(f"Query timeout on attempt {attempt + 1}: {e}")

            except aiohttp.ClientResponseError as e:
                if e.status in _NON_RETRYABLE_STATUSES:
                    # Client error (bad request, auth failure, etc.) — retrying
                    # won't help, so fail fast without consuming the retry budget.
                    logger.error(f"Non-retryable client error from {self.agent_url}: HTTP {e.status}")
                    raise QueryProcessingError(
                        f"Query rejected by {self.agent_url}: HTTP {e.status}",
                        {"status": e.status},
                        retryable=False,
                    ) from e
                last_exception = AgentNotFoundError(self.agent_url, e)
                logger.warning(f"Query server error on attempt {attempt + 1}: HTTP {e.status}: {e}")

            except aiohttp.ClientError as e:
                last_exception = AgentNotFoundError(self.agent_url, e)
                logger.warning(f"Query connection error on attempt {attempt + 1}: {e}")

            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")

            # Wait before retry (except on last attempt)
            if attempt < self.max_retries:
                wait_time = 2**attempt  # Exponential backoff
                logger.info(f"Retrying in {wait_time}s...")
                await asyncio.sleep(float(wait_time))

        # All retries exhausted
        logger.error(f"Query failed after {self.max_retries + 1} attempts")
        raise last_exception or AgentNotFoundError(self.agent_url)

    async def query_agent_stream(
        self,
        query: str,
        context: dict[str, object] | None = None,
        session_id: str | None = None,
        max_results: int = 10,
        similarity_threshold: float = 0.7,
        **kwargs: object,
    ) -> AsyncGenerator[dict[str, object]]:
        """
        Stream query results from the agent's streaming endpoint.

        Args:
            query: The user's question or query to be processed.
            context: Optional context information.
            session_id: Optional session identifier.
            max_results: Maximum number of results to return.
            similarity_threshold: Minimum similarity threshold.
            **kwargs: Additional parameters forwarded to the API.

        Yields:
            Stream events from the query processing:
            - {"type": "token", "content": "..."}
            - {"type": "result", "content": "...", "query_id": "..."}
            - {"type": "done", "processing_time_ms": 123.4, "session_id": "..."}
            - {"type": "error", "error": "...", "message": "..."}

        Raises:
            AgentNotFoundError: Agent is unreachable / endpoint not found.
            AgentTimeoutError: Request exceeded timeout.
            QueryProcessingError: Query processing failed.
        """
        await self._ensure_session()
        assert self._session is not None

        # Build request payload
        request_data = {
            "query": query,
            "max_results": max_results,
            "similarity_threshold": similarity_threshold,
        }

        if context is not None:
            request_data["context"] = context
        if session_id is not None:
            request_data["session_id"] = session_id

        request_data.update(kwargs)

        stream_url = f"{self.agent_url}/api/v1/query/stream"
        logger.info(f"Streaming query from agent: {stream_url}")

        try:
            async with self._session.post(
                stream_url,
                json=request_data,
                headers=self.auth_headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                if response.status == 404:
                    raise AgentNotFoundError(self.agent_url)

                response.raise_for_status()

                # Parse Server-Sent Events
                async for line in response.content:
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue

                    if line_str.startswith("event: "):
                        # SSE event type - currently not used but available for future extension
                        _ = line_str[7:]
                        continue

                    if line_str.startswith("data: "):
                        try:
                            data = json.loads(line_str[6:])
                            yield data
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse SSE data: {line_str}")
                            continue

        except TimeoutError as e:
            raise AgentTimeoutError(self.agent_url, self.timeout) from e
        except aiohttp.ClientResponseError as e:
            if e.status in _NON_RETRYABLE_STATUSES:
                logger.error(f"Non-retryable client error from {self.agent_url}: HTTP {e.status}")
                raise QueryProcessingError(
                    f"Query rejected by {self.agent_url}: HTTP {e.status}",
                    {"status": e.status},
                    retryable=False,
                ) from e
            raise AgentNotFoundError(self.agent_url, e) from e
        except aiohttp.ClientError as e:
            raise AgentNotFoundError(self.agent_url, e) from e

    async def health_check(self) -> bool:
        """
        Check whether the agent health endpoint returns a 2xx status.

        Returns:
            True if agent is healthy
        """
        await self._ensure_session()
        assert self._session is not None

        health_url = f"{self.agent_url}/health"

        try:
            async with self._session.get(health_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                return 200 <= response.status < 300
        except Exception as e:
            logger.debug(f"Health check failed for {self.agent_url}: {e}")
            return False

    async def close(self):
        """Close the HTTP session"""
        if self._owns_session and self._session:
            await self._session.close()
