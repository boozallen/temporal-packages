# Foundry Temporal

Core Temporal workflow utilities providing framework-agnostic components for building robust, observable workflows with human-in-the-loop patterns.

## Overview

This package provides reusable baseline components for building Temporal-based workflows with any agent framework. It is completely independent of specific agent implementations and focuses on:

- **Activity Utilities**: Decorators and base classes for activities with observability, error classification, and heartbeating
- **Human-in-Loop Patterns**: Standardized signal/query patterns for approval workflows
- **Retry Policies**: Pre-configured retry policies for different operation types
- **Storage Abstraction**: Multi-backend storage supporting S3, DynamoDB, and local files
- **Data Models**: Pydantic models for document metadata with validation and serialization
- **Observability**: Prometheus metrics and structured logging
- **Error Handling**: Comprehensive error classification and wrapping
- **Worker Utilities**: Bootstrap and configuration helpers for Temporal workers

## Installation

```bash
pip install foundry-temporal
```

From your own package index (see [Adopting these packages](../../docs/foundry/releases/adopting.md)),
or straight from a release tag as the [root README](../../README.md#installation) shows.

## Quick Start

### Human-in-the-Loop Workflow

```python
import hashlib

from foundry_temporal import HILSignalsMixin, QueryMixin
from temporalio import workflow

@workflow.defn
class ApprovalWorkflow(HILSignalsMixin, QueryMixin):
    def __init__(self):
        super().__init__()

    @workflow.run
    async def run(self, document: str) -> str:
        # Generate initial draft
        draft = await self._create_draft(document)

        # Open the review with the draft's digest, then wait for human
        # approval (approve_plan with the same digest) or feedback
        self.open_plan_review(hashlib.sha256(draft.encode()).hexdigest())
        await workflow.wait_condition(self.is_plan_decision_received)

        if self.plan_approved:
            return await self._finalize_document(draft)
        else:
            # Handle feedback and retry
            revised_draft = await self._revise_draft(
                draft, self.plan_feedback_comments
            )
            self.reset_plan_feedback()
            # Continue approval cycle...
```

### Using Retry Policies

Temporal applies a retry policy where the workflow schedules the activity, not on
the activity definition:

```python
from datetime import timedelta

from foundry_temporal import HTTP_RETRY_POLICY, FILE_RETRY_POLICY
from temporalio import activity, workflow

@activity.defn
async def call_external_api() -> dict:
    pass

@activity.defn
async def save_document(content: str) -> str:
    pass

# Inside a workflow's run method:
# retries with exponential backoff for transient HTTP errors (5xx, timeouts, etc.)
data = await workflow.execute_activity(
    call_external_api,
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=HTTP_RETRY_POLICY,
)
# retry intervals suited to file system operations
path = await workflow.execute_activity(
    save_document,
    "content",
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=FILE_RETRY_POLICY,
)
```

### Storage Abstraction

```python
from foundry_temporal.storage import DocumentStorage
from foundry_temporal.models import DocumentMetadata

# Configure storage backend
storage = DocumentStorage(
    storage_type="dynamodb",
    table_name="workflow-documents",
    region="us-east-1",
)

# Store workflow documents
metadata = DocumentMetadata(
    workflow_id="workflow-123",
    version=1,
    doc_type="draft",
    document_key="research-plan",
    created_at="2024-01-01T12:00:00Z"
)

await storage.store_document(
    workflow_id="workflow-123",
    document_key="research-plan",
    content="# Research Plan\n...",
    metadata=metadata.model_dump()
)
```

### Activity Utilities

Standardized activity patterns with built-in observability and error classification:

```python
from foundry_temporal import foundry_activity, ActivityConfig

# Simple activity with observability + automatic error wrapping
@foundry_activity(config=ActivityConfig(enable_observability=True))
async def process_item(item_id: str) -> dict:
    result = await do_work(item_id)
    return {"status": "done", "item_id": item_id}
```

#### Long-Running Activities with Heartbeating

```python
from datetime import timedelta
from foundry_temporal import long_running_activity

@long_running_activity(heartbeat_interval=timedelta(seconds=10))
async def process_large_dataset(data: list[str]) -> dict[str, int]:
    results = {}
    for item in data:
        results[item] = await expensive_computation(item)
    return results
```

#### Class-Based Activities

```python
from foundry_temporal import BaseActivity, HeartbeatActivity, BatchActivity, ActivityConfig

# Subclass BaseActivity for full control
class MyActivity(BaseActivity):
    async def execute(self, input_data: str) -> str:
        return f"processed: {input_data}"

# Subclass BatchActivity for chunked processing with progress heartbeats
class DataIngestion(BatchActivity):
    async def process_batch(self, batch: list) -> list:
        return [await transform(item) for item in batch]

ingestion = DataIngestion(batch_size=50)
results = await ingestion(large_item_list)  # processes in chunks of 50
```

#### Error Classification

Activities automatically classify exceptions as retryable or non-retryable based on the error type (e.g. `TimeoutError`, `ConnectionError` → `RetryableError`; `ValueError` → `NonRetryableError`). This integrates with Temporal's retry policies so transient failures are retried while permanent failures fail fast.

## Key Components

### Signal Patterns (HILSignalsMixin)

`HILSignalsMixin` provides a full set of signals and helpers for human-in-the-loop workflows:

Every approval signal requires a non-empty `approver_id` and a `content_digest`
matching the digest of the content currently open for review; it is a silent
no-op otherwise (signal handlers must not raise). Call
`open_plan_review`/`open_document_review`/`open_review` with the digest of the
content being presented before the client sends the matching approve signal.
`cancel_workflow` and the feedback signals require `approver_id` but are not
phase- or digest-gated.

| Signal | Purpose |
|---|---|
| `approve_plan(approver_id, content_digest)` | Approve research plan, proceed to execution |
| `provide_plan_feedback(approver_id, comments)` | Request plan revision with feedback |
| `approve_research(approver_id, content_digest)` | Approve final document |
| `provide_feedback(approver_id, comments)` | Request document revision with feedback |
| `approve(approver_id, content_digest)` | General approval signal |
| `cancel_workflow(approver_id)` | Cancel the entire workflow |

| Helper Method | Purpose |
|---|---|
| `is_plan_decision_received()` | Check if plan was approved or feedback given |
| `is_document_decision_received()` | Check if document was approved or feedback given |
| `reset_plan_feedback()` | Clear plan feedback state for next iteration |
| `reset_document_feedback()` | Clear document feedback state for next iteration |

```python
# Open the plan lane with the digest of the plan under review, then wait
digest = hashlib.sha256(plan_text.encode()).hexdigest()
self.open_plan_review(digest)
await workflow.wait_condition(self.is_plan_decision_received)

# Client sends the matching signal with the same digest
handle = client.get_workflow_handle("my-workflow")
await handle.signal("approve_plan", args=["reviewer-1", digest])
await handle.signal(
    "provide_plan_feedback",
    args=["reviewer-1", "Please add more details on methodology"],
)
```

#### Custom Signal Factories

For workflows that need signals beyond the built-in set, use the factory functions instead of subclassing:

```python
from foundry_temporal import (
    create_approval_signal,
    create_feedback_signal,
    open_approval_review,
)
from temporalio import workflow

@workflow.defn
class CustomWorkflow:
    def __init__(self):
        self.deployment_approved = False  # set by the approve signal
        self.deployment_approved_by = None
        self.rollback_received = False
        self.rollback_comments = ""

    # Creates a @workflow.signal(approver_id, content_digest) that sets
    # self.deployment_approved / self.deployment_approved_by, bound to the
    # lane opened via open_approval_review(self, "deployment", digest)
    approve_deployment = create_approval_signal("deployment")

    # Creates a @workflow.signal(approver_id, comments) that sets
    # self.rollback_received / self.rollback_comments
    request_rollback = create_feedback_signal("provide_rollback")

    async def run(self):
        digest = hashlib.sha256(deployment_plan.encode()).hexdigest()
        open_approval_review(self, "deployment", digest)
        await workflow.wait_condition(lambda: self.deployment_approved)
```

### Query Patterns (QueryMixin)

Status queries for external monitoring:

```python
# Query workflow status from a client
handle = client.get_workflow_handle("my-workflow")
status = await handle.query("get_status")
# Returns: {
#   "workflow_id": "my-workflow",
#   "current_phase": "awaiting_approval",
#   "iteration": 2,
#   "approved": false,
#   "approved_by": null,
#   "plan_approved_by": null,
#   "document_approved_by": null,
#   "awaiting_feedback": true,
#   "current_document_key": null,
#   "last_updated": "2026-01-01T12:00:00+00:00"
# }
```

### Worker Configuration

Bootstrap workers with standardized configuration:

```python
from foundry_temporal.worker import WorkerConfig, create_worker_with_defaults, create_temporal_client

async def main():
    # Load configuration from environment
    config = WorkerConfig.from_env()

    # Log resolved config at startup
    print(config.to_dict())

    # Create Temporal client (requires an explicit TEMPORAL_TLS_MODE; see docs/tls-posture.md)
    client = await create_temporal_client(config)

    # Create worker with foundry defaults
    worker = create_worker_with_defaults(
        client=client,
        workflows=[MyWorkflow],
        activities=[my_activity],
        config=config
    )

    await worker.run()
```

`WorkerConfig.from_env()` reads all settings from environment variables:

| Variable | Default | Description |
|---|---|---|
| `TEMPORAL_HOST` | `localhost:7233` | Temporal frontend address |
| `TEMPORAL_NAMESPACE` | `default` | Temporal namespace |
| `TASK_QUEUE` | `foundry-workflows` | Worker task queue name |
| `MAX_CONCURRENT_ACTIVITIES` | `100` | Max concurrent activities |
| `MAX_CONCURRENT_WORKFLOW_TASKS` | `50` | Max concurrent workflow tasks |
| `MAX_CONCURRENT_LOCAL_ACTIVITIES` | `200` | Max concurrent local activities |
| `MAX_CONCURRENT_NEXUS_TASKS` | `10` | Max concurrent nexus tasks |
| `LOG_LEVEL` | `INFO` | Logging level |
| `METRICS_PORT` | `9090` | Prometheus metrics port |
| `HEALTH_PORT` | `9091` | Health check port |
| `TEMPORAL_TLS_MODE` | — | **Required.** Explicit TLS posture: `platform`, `off` (alias for `platform`), `tls`, or `mtls`. `create_temporal_client()` fails closed if unset/invalid. See [`docs/tls-posture.md`](docs/tls-posture.md) |
| `TEMPORAL_TLS_CERT` | — | TLS certificate path (used by `tls`/`mtls`; required for `mtls`) |
| `TEMPORAL_TLS_KEY` | — | TLS key path (required for `mtls`) |
| `TEMPORAL_TLS_CA` | — | TLS CA certificate path (optional for `tls`/`mtls`) |
| `WORKER_CONCURRENCY` | — | **Legacy** alias for `MAX_CONCURRENT_ACTIVITIES` (deprecated) |
| `FOUNDRY_TEMPORAL_MAX_COMMENTS_LEN` | `8192` | Maximum signal comment length before truncation (STIG V-222612) |
| `FOUNDRY_TEMPORAL_MAX_HEADER_VALUE_LEN` | `4096` | Maximum injected header value length (STIG V-222612) |
| `FOUNDRY_TEMPORAL_MAX_HEADER_COUNT` | `50` | Maximum number of injected headers per workflow start (STIG V-222612) |

### Observability

Integrated Prometheus metrics and structured logging.

> **Note:** Observability utilities are imported from `foundry_temporal.observability`, not from the top-level package. This avoids pulling `prometheus_client` into Temporal's workflow sandbox.

```python
from foundry_temporal.observability import start_metrics_server, time_agent_call, time_storage_operation, get_health_status
from foundry_temporal.logging import WorkflowEventLogger, setup_structured_logging

# Setup structured logging
logger = setup_structured_logging("INFO")

# Log workflow events with metrics
event_logger = WorkflowEventLogger("workflow-123")
event_logger.workflow_started(topic="research project")
event_logger.plan_generated(version=1, document_key="plan-v1")
event_logger.workflow_completed(status="success", iterations=2)

# Start Prometheus metrics server
start_metrics_server(port=9090)

# Time agent calls for metrics
with time_agent_call():
    result = await call_agent()

# Time storage operations with backend labels
with time_storage_operation(operation="store", backend="dynamodb"):
    await storage.store_document(workflow_id="wf-1", document_key="draft#1", content="...")

# Health check endpoint (e.g. for FastAPI /health route)
status = get_health_status()
# {'status': 'healthy', 'timestamp': '...', 'observability': {'prometheus_available': True, ...}, ...}
```

## Available Retry Policies

Pre-configured retry policies optimized for different operation types:

| Policy | Use Case | Initial Interval | Max Interval | Max Attempts |
|--------|----------|------------------|--------------|--------------|
| `HTTP_RETRY_POLICY` | API calls, web requests | 1s | 15s | 3 |
| `FILE_RETRY_POLICY` | File I/O operations | 1s | 5s | 3 |
| `PROCESSING_RETRY_POLICY` | Light computation | 1s | 10s | 3 |
| `DYNAMODB_RETRY_POLICY` | DynamoDB operations | 1s | 5s | 3 |

### Custom Retry Policies

```python
from datetime import timedelta

from foundry_temporal import get_retry_policy_for_activity
from temporalio import workflow

# Get appropriate policy by activity type ("http", "file", "processing", "dynamodb")
retry_policy = get_retry_policy_for_activity("http")

# Inside a workflow's run method:
await workflow.execute_activity(
    my_activity,
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=retry_policy,
)
```

## Storage Backends

### Encryption at Rest

Every backend encrypts document content with AES-256-GCM before it is written.
Set `FOUNDRY_TEMPORAL_ENCRYPTION_KEY` to a 64-character hex string (32 bytes)
before constructing a backend; construction fails if it is missing or malformed.

```bash
export FOUNDRY_TEMPORAL_ENCRYPTION_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

A custom backend inherits this by calling `super().__init__()`, storing
`self._encrypt_content(content)` instead of the raw content, and returning
`self._decrypt_content(stored)` on read. Reads of content that was stored
unencrypted fall back to returning it as plaintext, with a warning.

### Custom Backends (StorageBackend ABC)

Implement the `StorageBackend` abstract base class to add your own storage backend:

```python
from foundry_temporal.storage import StorageBackend
from foundry_temporal import DocumentMetadata

class RedisStorage(StorageBackend):
    async def store_document(self, workflow_id, document_key, content, metadata=None) -> str:
        ...
    async def retrieve_document(self, workflow_id, document_key) -> str:
        ...
    async def get_document_metadata(self, workflow_id, document_key) -> DocumentMetadata:
        ...
    async def list_documents(self, workflow_id, doc_type=None) -> list[DocumentMetadata]:
        ...
    async def get_latest_document_key(self, workflow_id, doc_type) -> str:
        ...
```

### DynamoDB Storage

```python
from foundry_temporal.storage import DynamoDBStorage

storage = DynamoDBStorage(
    table_name="workflow-docs",
    region="us-east-1",
)
```

### S3 Storage

```python
from foundry_temporal.storage import S3Storage

storage = S3Storage(
    bucket_name="workflow-artifacts",
    region="us-east-1",
)
```

### Local File Storage

```python
from foundry_temporal.storage import LocalFileStorage

storage = LocalFileStorage(
    base_path="/var/workflow-storage"
)
```

## Data Models

### DocumentMetadata

`DocumentMetadata` is the Pydantic model that every storage backend returns from `get_document_metadata()` and `list_documents()`. It tracks workflow document versions, approval state, and sizing information.

```python
from foundry_temporal import DocumentMetadata
```

#### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `workflow_id` | `str` | Yes | — | Workflow ID that created the document |
| `version` | `int` | Yes | — | Document version number |
| `doc_type` | `Literal["draft", "final"]` | Yes | — | Document lifecycle stage |
| `created_at` | `str` | Yes | — | Creation timestamp (ISO 8601) |
| `document_key` | `str` | Yes | — | Unique key in `{type}#{version}` format (e.g. `draft#1`) |
| `approved` | `bool` | No | `False` | Whether the document is approved |
| `updated_at` | `str \| None` | No | `None` | Last update timestamp (ISO 8601) |
| `content_size` | `int \| None` | No | `None` | Document content size in bytes |
| `iteration_count` | `int \| None` | No | `None` | Number of iterations/revisions |

#### Creating Metadata

```python
from foundry_temporal import DocumentMetadata

metadata = DocumentMetadata(
    workflow_id="research-workflow-123",
    version=1,
    doc_type="draft",
    created_at="2024-01-15T10:30:00Z",
    document_key="draft#1",
)

# Optional fields
metadata_full = DocumentMetadata(
    workflow_id="research-workflow-123",
    version=2,
    doc_type="final",
    created_at="2024-01-15T10:30:00Z",
    document_key="final#2",
    approved=True,
    updated_at="2024-01-16T14:00:00Z",
    content_size=4096,
    iteration_count=3,
)
```

#### Receiving Metadata from Storage

Storage backends construct and return `DocumentMetadata` instances. The `document_key` follows a `{type}#{version}` convention that the storage layer parses to populate `doc_type` and `version`:

```python
from foundry_temporal.storage import DocumentStorage

storage = DocumentStorage(storage_type="dynamodb", table_name="workflow-docs")

# Get metadata for a specific document
metadata = await storage.get_document_metadata(
    workflow_id="workflow-123",
    document_key="draft#1"
)
print(metadata.doc_type)       # "draft"
print(metadata.version)        # 1
print(metadata.approved)       # False

# List all documents (or filter by type)
all_docs = await storage.list_documents(workflow_id="workflow-123")
drafts = await storage.list_documents(workflow_id="workflow-123", doc_type="draft")

for doc in drafts:
    print(f"{doc.document_key} v{doc.version} — {doc.content_size} bytes")
```

#### Serialization

`DocumentMetadata` supports standard Pydantic serialization for passing data between activities, storing in signals, or returning from queries:

```python
# Serialize to dict (e.g. for Temporal activity input/output)
data = metadata.model_dump()
# {'workflow_id': 'research-workflow-123', 'version': 1, 'doc_type': 'draft', ...}

# Serialize to JSON string
import json
json_str = json.dumps(metadata.model_dump())

# Reconstruct from dict
restored = DocumentMetadata(**data)

# Pass as activity argument via model_dump()
await storage.store_document(
    workflow_id="workflow-123",
    document_key="draft#1",
    content="# Research Plan\n...",
    metadata=metadata.model_dump()
)
```

#### Validation

Pydantic enforces types and required fields at construction time:

```python
from pydantic import ValidationError

# Missing required field → ValidationError
try:
    DocumentMetadata(version=1, doc_type="draft", created_at="2024-01-15T10:30:00Z", document_key="draft#1")
except ValidationError as e:
    print(e)  # workflow_id is required

# Invalid doc_type → ValidationError
try:
    DocumentMetadata(
        workflow_id="wf-1", version=1, doc_type="review",
        created_at="2024-01-15T10:30:00Z", document_key="review#1"
    )
except ValidationError as e:
    print(e)  # doc_type must be 'draft' or 'final'
```

## Error Handling

The error hierarchy gives activities a two-axis choice: **what kind of failure** (error class) and **should Temporal retry** (`non_retryable` flag). The error class tells the API layer which HTTP status to return, while the flag tells Temporal whether to retry — two concerns, one raise statement.

### Error Types

| Error Class | Default Retry | Use Case |
|---|---|---|
| `AgentError` | Non-retryable | Upstream agent failures |
| `StorageError` | Non-retryable | S3/DynamoDB/file system failures |
| `ConfigurationError` | Non-retryable (always) | Missing env vars, bad config |
| `ValidationError` | Non-retryable (always) | Bad user input |
| `RetryableError` | Retryable (always) | Any transient failure |
| `NonRetryableError` | Non-retryable (always) | Any permanent failure |

### Using Error Types in Activities

Pick the error class for the failure domain, and override `non_retryable` for transient cases:

```python
from foundry_temporal import AgentError, StorageError, ConfigurationError, ValidationError
from temporalio import activity

@activity.defn
async def call_research_agent(agent_url: str, task: str) -> dict:
    if not agent_url:
        raise ConfigurationError("AGENT_URL not set")  # never retries
    if not task:
        raise ValidationError("task cannot be empty")  # never retries

    try:
        result = await http_client.post(agent_url, json={"task": task})
        return result.json()
    except httpx.TimeoutException:
        # Transient — Temporal will retry
        raise AgentError(f"Agent timeout: {agent_url}", non_retryable=False)
    except httpx.HTTPStatusError as e:
        if e.response.status_code >= 500:
            raise AgentError(f"Agent server error: {e}", non_retryable=False)
        else:
            raise AgentError(f"Agent protocol error: {e}")  # permanent, no retry

@activity.defn
async def save_results(bucket: str, key: str, data: str) -> None:
    try:
        await s3_client.put_object(Bucket=bucket, Key=key, Body=data)
    except s3_client.exceptions.NoSuchBucket:
        raise StorageError(f"Bucket {bucket} not found")  # permanent
    except Exception as e:
        raise StorageError(f"S3 write failed: {e}", non_retryable=False)  # transient
```

### Handling Errors in FastAPI

Register type-specific exception handlers so each error class maps to the right HTTP status:

```python
from foundry_temporal import AgentError, StorageError, ConfigurationError, ValidationError, WorkflowError

@app.exception_handler(AgentError)
async def agent_error_handler(request, exc):
    return JSONResponse(status_code=502, content={"error": "agent_error", "detail": str(exc)})

@app.exception_handler(StorageError)
async def storage_error_handler(request, exc):
    return JSONResponse(status_code=503, content={"error": "storage_error", "detail": str(exc)})

@app.exception_handler(ValidationError)
async def validation_error_handler(request, exc):
    return JSONResponse(status_code=422, content={"error": "validation_error", "detail": str(exc)})

@app.exception_handler(WorkflowError)
async def workflow_error_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": "workflow_error", "detail": str(exc)})
```

### Error Factory Functions

When you already know whether a failure is transient or permanent, use the convenience factories to build an error with the original exception's message attached:

```python
from foundry_temporal import create_retryable_error, create_non_retryable_error

try:
    await external_service.call()
except TimeoutError as e:
    raise create_retryable_error("Service timed out", original_error=e)
except ValueError as e:
    raise create_non_retryable_error("Bad payload", original_error=e)
```

### Automatic Error Classification

For cases where you don't want to pick the error type manually, use `classify_and_wrap_error` to auto-detect retryability:

```python
from foundry_temporal import classify_and_wrap_error, is_retryable_error

try:
    result = await external_call()
except Exception as e:
    # Automatically wraps as RetryableError or NonRetryableError
    # based on the exception type (ConnectionError → retryable, ValueError → non-retryable)
    raise classify_and_wrap_error(e, "External API call")
```

## Architecture Integration

### With Agent Frameworks

```python
# Use with any agent framework
from foundry_temporal import HILSignalsMixin
from foundry_temporal_agents.activities import call_strands_agent  # Strands

@workflow.defn
class AgentWorkflow(HILSignalsMixin):
    # Framework-agnostic HIL patterns
    # + agent-specific integration
    pass
```

### Environment Configuration

All worker and observability environment variables are listed in the [Worker Configuration](#worker-configuration) table above. Storage backends read one more, the content key described in [Encryption at Rest](#encryption-at-rest):

```bash
# Storage (every backend)
FOUNDRY_TEMPORAL_ENCRYPTION_KEY=<64-character hex string>
```

The table name, bucket name, and region are constructor arguments, not environment
variables (see [DynamoDB Storage](#dynamodb-storage) and [S3 Storage](#s3-storage)).

## Testing

Run the comprehensive test suite:

```bash
pytest tests/ -v --cov=src --cov-report=term-missing
# unit and integration tiers, covering all components
```

## Development

This package is part of the Foundry temporal packages monorepo:

```bash
# Install in development mode
uv pip install -e .

# Run tests with coverage
just test

# Run specific test modules
pytest tests/unit/test_signals.py -v --no-cov
pytest tests/unit/test_storage.py -v --no-cov
pytest tests/unit/test_observability.py -v --no-cov
```

## Production Considerations

### Monitoring

The package includes comprehensive observability:

- **Metrics**: Workflow completion rates, retry counts, duration histograms
- **Logging**: Structured logs with workflow context
- **Health Checks**: Built-in health endpoints for load balancers

### Scaling

- Worker concurrency configurable per activity type
- Storage backends designed for high throughput
- Retry policies tuned for production loads

### Security

- No hardcoded credentials (environment-based configuration)
- Explicit TLS posture required for Temporal connections (`TEMPORAL_TLS_MODE`; see [`docs/tls-posture.md`](docs/tls-posture.md))
- Document content encrypted at rest in every storage backend (`FOUNDRY_TEMPORAL_ENCRYPTION_KEY`)
- IAM-based access control for cloud storage backends

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Contributing

See the repository [CONTRIBUTING.md](../../CONTRIBUTING.md).
