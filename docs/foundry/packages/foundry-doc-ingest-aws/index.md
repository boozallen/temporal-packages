# foundry-doc-ingest-aws

![Status: Available](https://img.shields.io/badge/status-available-brightgreen)
![Version](https://img.shields.io/badge/version-0.2.0-blue)
![Python](https://img.shields.io/badge/python-3.14%20%7C%203.15-blue)

AWS integration for document ingestion: upload documents to S3 and sync
them into a Bedrock Knowledge Base from a Temporal workflow. **Depends on:**
[`foundry-doc-ingest`](../foundry-doc-ingest/index.md).

## Install

Install a released wheel from this repo's
[GitHub Releases](https://github.com/boozallen/temporal-packages/releases).
See [Adopting these packages](../../releases/adopting.md) for
the full flow - installing from a release tag for evaluation, or hosting
the wheel in your own index for production, plus verifying the SBOM.

## Quickstart

Call `upload_to_s3` from your API layer before starting the workflow.
Register `trigger_kb_sync` and `wait_for_indexing` on your worker; they are
synchronous, so give the worker an `activity_executor`.

```python
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class SyncKnowledgeBaseWorkflow:
    @workflow.run
    async def run(self, knowledge_base_id: str, data_source_id: str) -> None:
        job_id = await workflow.execute_activity(
            "trigger_kb_sync",
            args=[knowledge_base_id, data_source_id],
            start_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.execute_activity(
            "wait_for_indexing",
            args=[knowledge_base_id, data_source_id, job_id],
            start_to_close_timeout=timedelta(seconds=320),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3, non_retryable_error_types=["RuntimeError"]),
        )
```

## What's in the box

| Surface | Highlights |
|---------|------------|
| S3 upload | `upload_to_s3`: uploads under a UUID-suffixed key and returns the key |
| Knowledge Base sync | `trigger_kb_sync` starts an ingestion job; `wait_for_indexing` polls it and raises `RuntimeError` if it fails or `TimeoutError` past `timeout` |
| Testability | Optional `s3_client` / `bedrock_client` overrides |

## Security

- **No credentials in code**: clients use the standard AWS credential chain.
- **Least privilege**: the API role needs `s3:PutObject`; the worker role needs
  `bedrock:StartIngestionJob` and `bedrock:GetIngestionJob`.

## Reference

- [README](../../../../packages/foundry-doc-ingest-aws/README.md)
- [Changelog](../../../../packages/foundry-doc-ingest-aws/CHANGELOG.md)
- [Source](../../../../packages/foundry-doc-ingest-aws/)
- [License (Apache-2.0)](../../../../LICENSE)
