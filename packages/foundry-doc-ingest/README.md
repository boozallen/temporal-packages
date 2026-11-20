# foundry-doc-ingest

Document ingestion activities for Temporal workflows. Provides file validation, local storage, and SQLite provenance tracking with zero cloud dependencies.

## Install

```bash
pip install foundry-doc-ingest
```

From your own package index (see [Adopting these packages](../../docs/foundry/releases/adopting.md)),
or straight from a release tag as the [root README](../../README.md#installation) shows.

Requires Python 3.14 or 3.15. The only runtime dependency is `temporalio`.

## Usage

Register the activities on your Temporal worker. They are synchronous
functions, so the worker needs an `activity_executor` to run them:

```python
from concurrent.futures import ThreadPoolExecutor

from foundry_doc_ingest import validate_file, store_file, update_provenance

worker = Worker(
    client=client,
    task_queue="doc-ingest",
    activities=[validate_file, store_file, update_provenance],
    activity_executor=ThreadPoolExecutor(max_workers=10),
)
```

Call them from a workflow via `execute_activity`:

```python
from temporalio import workflow
from temporalio.exceptions import ApplicationError
from datetime import timedelta

@workflow.defn
class IngestWorkflow:
    @workflow.run
    async def run(self, file_path: str) -> str:
        result = await workflow.execute_activity(
            "validate_file",
            args=[file_path, None],
            start_to_close_timeout=timedelta(seconds=30),
        )
        if not result["valid"]:
            raise ApplicationError(result["error"], non_retryable=True)

        stored_path = await workflow.execute_activity(
            "store_file",
            args=[file_path, "/data/ingested"],
            start_to_close_timeout=timedelta(seconds=60),
        )

        await workflow.execute_activity(
            "update_provenance",
            args=[workflow.info().workflow_id, stored_path, "ingest", "success", "/data/provenance.db"],
            start_to_close_timeout=timedelta(seconds=30),
        )
        return stored_path
```

## API Reference

### Activities

#### `validate_file(file_path, supported_extensions=None) -> ValidationResult`

Validates that a file exists, is non-empty, and has a supported extension.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | `str` | — | Path to the file to validate |
| `supported_extensions` | `list[str] \| None` | `[".pdf", ".txt", ".docx", ".md", ".json"]` | Allowed extensions |

Returns a `ValidationResult` dataclass.

#### `store_file(source_path, target_dir="/tmp") -> str`

Copies a file to local storage with a UUID-based unique name to avoid collisions. Creates the target directory if it does not exist.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_path` | `str` | — | Path to the source file |
| `target_dir` | `str` | `"/tmp"` | Directory to store the copy |

Returns the absolute path to the stored file.

Raises `FileNotFoundError` if `source_path` does not exist.

#### `update_provenance(workflow_id, file_reference, step_name, outcome, db_path=None) -> None`

Writes a timestamped provenance record to the SQLite database.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `workflow_id` | `str` | — | Temporal workflow ID |
| `file_reference` | `str` | — | Path or identifier for the file |
| `step_name` | `str` | — | Name of the workflow step |
| `outcome` | `str` | — | Result of the step (e.g., `"success"`, `"failed"`) |
| `db_path` | `str \| None` | System temp dir | SQLite database path |

### Utilities

#### `get_provenance(workflow_id, db_path=None) -> list[ProvenanceRecord]`

Queries provenance records by workflow ID, ordered by timestamp.

#### `init_provenance_db(db_path=None) -> None`

Initializes the provenance database and table. Safe to call multiple times (no-op after first call for a given path).

### Data Classes

#### `ValidationResult`

| Field | Type | Description |
|-------|------|-------------|
| `valid` | `bool` | Whether the file passed validation |
| `file_path` | `str` | The path that was validated |
| `error` | `str \| None` | Error message if validation failed |

#### `ProvenanceRecord`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Auto-increment row ID |
| `workflow_id` | `str` | Temporal workflow ID |
| `file_reference` | `str` | File path or identifier |
| `step_name` | `str` | Workflow step name |
| `outcome` | `str` | Step result |
| `timestamp` | `str` | ISO 8601 UTC timestamp |
