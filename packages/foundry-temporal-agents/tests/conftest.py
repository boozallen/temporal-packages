# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Test configuration and fixtures for foundry_temporal_agents tests"""

import asyncio
import dataclasses
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest


def _to_temporal_style_input(typed_input: Any) -> dict[str, Any]:
    """
    Convert a typed activity input to the dict form Temporal's default converter
    gives the worker after deserialization.
    """
    if hasattr(typed_input, "model_dump"):
        return typed_input.model_dump()
    if dataclasses.is_dataclass(typed_input):
        return dataclasses.asdict(typed_input)
    raise TypeError(f"temporal_style_input expects a dataclass or Pydantic model, got {type(typed_input)}")


@pytest.fixture
def temporal_style_input() -> Callable[[Any], dict[str, Any]]:
    """
    Converter that simulates the "Temporal path": workflow sends a typed payload
    → serialized on wire → worker receives dict. Any activity that accepts a
    dataclass/Pydantic input must be tested with dict input produced by this
    converter to catch serialization/coercion bugs.
    """
    return _to_temporal_style_input


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def _foundry_tls_mode_off(monkeypatch):
    """Default FOUNDRY_TLS_MODE=platform for all tests unless overridden."""
    monkeypatch.setenv("FOUNDRY_TLS_MODE", "platform")


@pytest.fixture
def mock_agent_response():
    """Standard mock agent response"""
    return {
        "status": "completed",
        "result": "Task completed successfully",
        "summary": "Processed the request",
        "metadata": {"processing_time": 1.5},
    }


@pytest.fixture
def mock_agent_capabilities():
    """Standard mock agent capabilities"""
    return {
        "name": "test-agent",
        "description": "A test agent for unit tests",
        "version": "1.0.0",
        "capabilities": ["text_processing", "data_analysis"],
        "tools": ["file_reader", "web_search", "calculator"],
        "features": ["streaming", "async_processing", "batch_processing"],
    }


@pytest.fixture
def mock_a2a_response():
    """Standard mock A2A protocol response"""
    return {"jsonrpc": "2.0", "result": {"status": "completed", "result": "Task completed successfully"}, "id": 1}


@pytest.fixture
def mock_http_session():
    """Mock aiohttp ClientSession"""
    session = AsyncMock()

    # Mock successful response by default
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "jsonrpc": "2.0",
        "result": {"status": "completed", "data": "test response"},
        "id": 1,
    }
    mock_response.__aenter__.return_value = mock_response

    session.post.return_value = mock_response
    session.get.return_value = mock_response

    return session


@pytest.fixture
def test_agent_url():
    """Standard test agent URL"""
    return "http://test-agent.example.com"


@pytest.fixture
def sample_task_data():
    """Sample task data for testing"""
    return {
        "task": "Process this document",
        "context": {"file_path": "/tmp/test_document.pdf", "format": "pdf", "priority": "high"},
        "session_id": "test-session-123",
    }


class AsyncContextManagerMock:
    """Helper class for mocking async context managers"""

    def __init__(self, return_value=None):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def async_context_manager():
    """Factory for creating async context manager mocks"""
    return AsyncContextManagerMock
