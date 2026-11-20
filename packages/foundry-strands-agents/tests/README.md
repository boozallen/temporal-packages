# Tests for foundry_strands_agents

This directory contains comprehensive unit tests for the foundry_strands_agents package.

## Test Structure

Tests are tiered by directory: [`tests/unit/`](unit/) is the fast, credential-free tier
and [`tests/integration/`](integration/) holds tests needing external services or credentials.
[`conftest.py`](conftest.py) stays at the `tests/` root so its fixtures reach both tiers.

- [`unit/test_exceptions.py`](unit/test_exceptions.py) - Tests for custom exception classes
- [`unit/test_protocols.py`](unit/test_protocols.py) - Tests for A2A protocol message handling
- [`unit/test_client.py`](unit/test_client.py) - Tests for the HTTP client that communicates with agents
- [`unit/test_discovery.py`](unit/test_discovery.py) - Tests for agent capability discovery and registry
- [`unit/test_agent_activities.py`](unit/test_agent_activities.py) - Tests for Temporal activity decorators and functions
- [`unit/test_query_activities.py`](unit/test_query_activities.py) - Tests for Strands Query API activities
- [`unit/test_query_client.py`](unit/test_query_client.py) - Tests for the Strands Query API client
- [`unit/test_query_models.py`](unit/test_query_models.py) - Tests for Query API request/response models
- [`unit/test_tls.py`](unit/test_tls.py) - Tests for TLS configuration helpers
- [`unit/test_init.py`](unit/test_init.py) - Tests for package imports and initialization
- [`conftest.py`](conftest.py) - Test fixtures and configuration

## Running Tests

From the package root directory:

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=foundry_strands_agents --cov-report=term-missing

# Run one tier
pytest tests/unit
pytest tests/integration

# Run specific test file
pytest tests/unit/test_client.py
```

## Test Categories

The unit/integration split is by directory (`tests/unit/`, `tests/integration/`),
not by marker. Markers remain for cross-cutting traits that a directory cannot
express:

- `slow` - Tests that take longer to execute
- `network` - Tests that require network access
- `temporal` - Tests that require Temporal server
- `aws` - Tests that interact with AWS services

## Dependencies

Test dependencies are managed in the main pyproject.toml file. Key testing libraries:

- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting

## Mock Usage

Tests extensively use mocking to avoid dependencies on external services:

- HTTP requests are mocked using `unittest.mock.AsyncMock`
- Temporal activities are tested without actual Temporal server
- Agent responses are simulated with controlled mock data

## Coverage Goals

Tests aim for high coverage of:

- All public API functions and methods
- Error handling and edge cases
- Async/await patterns
- Protocol compliance (A2A)
- Configuration validation