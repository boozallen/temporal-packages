# Foundry Temporal Test Suite

Comprehensive unit tests for the `foundry_temporal` package, covering all core functionality including error handling, models, retry policies, signals, queries, observability, storage abstraction, and worker configuration.

## Test Structure

```
tests/
├── conftest.py                  # Shared fixtures, visible to both tiers
├── unit/                        # Fast, credential-free tier
│   ├── test_errors.py           # Error classification and handling tests
│   ├── test_models.py           # Pydantic model validation tests
│   ├── test_retry.py            # Retry policy configuration tests
│   ├── test_signals.py          # Human-in-loop signal pattern tests
│   ├── test_queries.py          # Workflow query functionality tests
│   ├── test_observability.py    # Logging and metrics integration tests
│   ├── test_storage.py          # Storage abstraction and backend tests
│   └── test_worker.py           # Worker configuration and bootstrap tests
├── integration/                 # Tests needing external services or credentials
└── README.md                    # This documentation
```

## Test Coverage

### Error Handling ([`unit/test_errors.py`](unit/test_errors.py))
- **Error Classification**: Tests automatic error classification system
- **HTTP Error Integration**: Tests integration with httpx and requests libraries
- **Retry Policy Integration**: Tests error-based retry policy selection
- **Custom Exceptions**: Tests custom exception hierarchy

### Data Models ([`unit/test_models.py`](unit/test_models.py))
- **DocumentMetadata Model**: Tests Pydantic model validation
- **Field Validation**: Tests required fields, type validation, and constraints
- **Serialization**: Tests JSON serialization/deserialization
- **Schema Generation**: Tests JSON schema generation with examples

### Retry Policies ([`unit/test_retry.py`](unit/test_retry.py))
- **Policy Configuration**: Tests retry policy constants and configuration
- **Policy Selection**: Tests activity-type-based retry policy selection
- **Parameter Validation**: Tests retry parameters (intervals, attempts, backoff)
- **Error Handling**: Tests invalid activity type handling

### Signal Patterns ([`unit/test_signals.py`](unit/test_signals.py))
- **HIL Signals Mixin**: Tests human-in-loop workflow signal patterns
- **State Management**: Tests approval/feedback state transitions
- **Signal Decorators**: Tests Temporal workflow signal decorators
- **Factory Functions**: Tests dynamic signal creation utilities

### Query Functionality ([`unit/test_queries.py`](unit/test_queries.py))
- **Query Mixin**: Tests workflow query mixin functionality
- **Status Reporting**: Tests workflow status query implementation
- **Attribute Handling**: Tests default attribute management
- **Temporal Integration**: Tests workflow.query decorator integration

### Observability ([`unit/test_observability.py`](unit/test_observability.py))
- **Structured Logging**: Tests logger wrapper and context binding
- **Metrics Integration**: Tests Prometheus metrics integration
- **Context Managers**: Tests timing and measurement context managers
- **Activity Logging**: Tests activity execution logging decorators

### Storage Abstraction ([`unit/test_storage.py`](unit/test_storage.py))
- **Abstract Base Class**: Tests storage backend interface
- **DynamoDB Backend**: Tests DynamoDB storage implementation with mocking
- **S3 Backend**: Tests S3 storage implementation with mocking
- **Local File Backend**: Tests local filesystem storage implementation
- **Factory Pattern**: Tests DocumentStorage factory class

### Worker Configuration ([`unit/test_worker.py`](unit/test_worker.py))
- **Configuration Management**: Tests WorkerConfig class and environment loading
- **Legacy Support**: Tests deprecated environment variable handling
- **Client Creation**: Tests Temporal client creation utilities
- **Worker Bootstrap**: Tests worker creation with default configuration

## Running Tests

### Prerequisites

Install test dependencies:
```bash
pip install pytest pytest-asyncio pytest-cov pytest-mock
```

### Run All Tests
```bash
pytest
```

### Run One Tier
The unit/integration split is by directory, not by marker.
```bash
pytest tests/unit
pytest tests/integration
```

### Run Specific Test Modules
```bash
pytest tests/unit/test_errors.py
pytest tests/unit/test_models.py
pytest tests/unit/test_storage.py
```

### Skip Cross-Cutting Traits
Markers remain for traits no directory expresses.
```bash
pytest -m "not slow"
```

### Coverage Reporting
```bash
# Generate HTML coverage report
pytest --cov=foundry_temporal --cov-report=html

# Generate terminal coverage report
pytest --cov=foundry_temporal --cov-report=term-missing

# Fail if coverage below 85%
pytest --cov=foundry_temporal --cov-fail-under=85
```

### Async Test Support
All async tests use `pytest-asyncio` for proper handling:
```python
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

## Test Patterns and Best Practices

### Mocking Strategy
- **External Dependencies**: All external services (AWS, Temporal, HTTP) are mocked
- **Shared Fixtures**: Common mocks are provided in [`conftest.py`](conftest.py)
- **Isolation**: Tests are fully isolated with no shared state

### Async Testing
- Uses `pytest-asyncio` for async test support
- Mocks async operations with `AsyncMock`
- Tests both success and error scenarios for async operations

### Error Scenario Testing
- Comprehensive error handling validation
- Tests for proper error classification and wrapping
- Validation of retry behavior and error recovery

### Configuration Testing
- Environment variable handling and precedence
- Legacy configuration support and deprecation warnings
- Configuration serialization and validation

## Fixtures and Utilities

### Core Fixtures (`conftest.py`)
- `sample_workflow_id`: Standard workflow ID for testing
- `sample_document_metadata`: Sample DocumentMetadata instance
- `mock_temporal_client`: Mock Temporal client
- `mock_dynamodb_table`: Mock DynamoDB table with standard responses
- `worker_config`: Sample WorkerConfig for testing
- `temp_directory`: Temporary directory for file operations

### Mock Utilities
- `mock_aiohttp_session`: Mock HTTP session for client testing
- `mock_metrics_client`: Mock Prometheus metrics client
- `mock_logger`: Mock structured logger
- `sample_error_responses`: Common error scenarios for testing

### Environment Management
- `mock_environment_variables`: Context manager for environment variable testing
- Automatic cleanup after test completion
- Support for testing environment variable precedence

## Integration Testing

While most tests are unit tests with mocking, integration test patterns are provided for:

### Storage Integration
- Tests that verify storage backend interface consistency
- Document key parsing consistency across operations
- Error classification integration with storage operations

### Worker Integration
- Complete worker setup flow testing
- Configuration serialization for logging
- Environment variable precedence testing

### Temporal Integration
- Signal decorator verification
- Query decorator verification
- Client and worker configuration integration

## Performance Considerations

### Test Execution Speed
- External dependencies are mocked to avoid network calls
- File operations use temporary directories
- Database operations are mocked for fast execution

### Resource Management
- Proper cleanup of temporary resources
- Mock object lifecycle management
- Memory-efficient test fixtures

## Debugging and Troubleshooting

### Verbose Test Output
```bash
pytest -v --tb=long
```

### Debug Specific Test
```bash
pytest tests/unit/test_storage.py::TestDynamoDBStorage::test_store_document_success -s
```

### Coverage Analysis
```bash
pytest --cov=foundry_temporal --cov-report=html
open htmlcov/index.html
```

### Performance Profiling
```bash
pytest --durations=10  # Show 10 slowest tests
```

## Continuous Integration

The test suite is designed for CI/CD environments:

### GitHub Actions Example
```yaml
- name: Run Tests
  run: |
    pytest --cov=foundry_temporal --cov-report=xml --cov-fail-under=85
- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

### Quality Gates
- Minimum 85% test coverage required
- All tests must pass
- No undefined markers allowed
- Strict configuration validation

## Contributing

### Adding New Tests
1. Follow existing test naming conventions (`test_*.py`), and place the file
   in the `tests/unit/` or `tests/integration/` tier it belongs to
2. Use appropriate fixtures from [`conftest.py`](conftest.py)
3. Add new fixtures to [`conftest.py`](conftest.py) if reusable
4. Include both success and error scenarios
5. Mock external dependencies
6. Add trait markers where they apply

### Test Tiers and Traits
The tier is the directory: put a new test in `tests/unit/` unless it needs
external services or credentials, in which case it goes in
`tests/integration/`. Markers are for cross-cutting traits only:
- `@pytest.mark.slow`: Tests that take significant time
- `@pytest.mark.network`: Tests requiring network access
- `@pytest.mark.aws`: Tests that interact with AWS services
- `@pytest.mark.temporal`: Tests that interact with Temporal services

### Code Quality
- Follow existing mocking patterns
- Ensure proper test isolation
- Include comprehensive error scenario testing
- Validate both positive and negative cases
- Use descriptive test names that explain the scenario being tested
