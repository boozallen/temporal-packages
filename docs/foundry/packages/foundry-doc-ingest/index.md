# foundry-doc-ingest

![Status: Available](https://img.shields.io/badge/status-available-brightgreen)
![Version](https://img.shields.io/badge/version-0.2.0-blue)
![Python](https://img.shields.io/badge/python-3.14%20%7C%203.15-blue)

Document ingestion activities for Temporal workflows: file validation,
local storage, and SQLite provenance tracking, with no cloud dependencies.
**No runtime dependencies on other packages in this repo.**

## Install

Install a released wheel from this repo's
[GitHub Releases](https://github.com/boozallen/temporal-packages/releases).
See [Adopting these packages](../../releases/adopting.md) for
the full flow - installing from a release tag for evaluation, or hosting
the wheel in your own index for production, plus verifying the SBOM.

## Quickstart

Register `validate_file`, `store_file`, and `update_provenance` on your
worker. They are synchronous, so give the worker an `activity_executor`
(for example, a `ThreadPoolExecutor`).

```python
from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ApplicationError


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

## What's in the box

| Surface | Highlights |
|---------|------------|
| Validation | `validate_file`: file exists, is non-empty, and has an allowed extension |
| Storage | `store_file`: copies a file into a target directory under a UUID-suffixed name |
| Provenance | `update_provenance`, `get_provenance`, `init_provenance_db` (SQLite) |
| Data classes | `ValidationResult`, `ProvenanceRecord` |

## Security

- **Extension allowlist**: `validate_file` rejects extensions outside
  `supported_extensions`.
- **Parameterized SQL**: provenance queries use bound parameters.
- **Explicit paths**: `store_file` defaults to `/tmp` and the provenance
  database to the system temp directory; pass your own `target_dir` and
  `db_path` in production.

## Reference

- [README](../../../../packages/foundry-doc-ingest/README.md)
- [Changelog](../../../../packages/foundry-doc-ingest/CHANGELOG.md)
- [Source](../../../../packages/foundry-doc-ingest/)
- [License (Apache-2.0)](../../../../LICENSE)
