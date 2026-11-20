# foundry-doc-ingest-aws

AWS integration for document ingestion — S3 upload and Bedrock Knowledge Base sync.

## Install

```bash
pip install foundry-doc-ingest-aws
```

From your own package index (see [Adopting these packages](../../docs/foundry/releases/adopting.md)),
or straight from a release tag as the [root README](../../README.md#installation) shows.

Requires Python 3.14 or 3.15. Depends on `boto3`, `temporalio`, and [`foundry-doc-ingest`](../foundry-doc-ingest/).

## Usage

### S3 upload

`upload_to_s3` is a plain function, not a Temporal activity — call it from
the API layer before a workflow starts:

```python
from foundry_doc_ingest_aws import upload_to_s3

s3_key = upload_to_s3(
    file_path="/tmp/report.pdf",
    bucket="my-ingest-bucket",
    key_prefix="incoming/",
)
```

### Bedrock Knowledge Base sync

`trigger_kb_sync` and `wait_for_indexing` are Temporal activities. They are
synchronous functions, so register them on a worker with an
`activity_executor`:

```python
from concurrent.futures import ThreadPoolExecutor

from foundry_doc_ingest_aws import trigger_kb_sync, wait_for_indexing

worker = Worker(
    client=client,
    task_queue="doc-ingest-aws",
    activities=[trigger_kb_sync, wait_for_indexing],
    activity_executor=ThreadPoolExecutor(max_workers=10),
)
```

Call them from a workflow via `execute_activity`:

```python
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta

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
            # A FAILED ingestion job raises RuntimeError; don't re-poll it forever
            retry_policy=RetryPolicy(maximum_attempts=3, non_retryable_error_types=["RuntimeError"]),
        )
```

`data_source_id` must match between the two calls — `wait_for_indexing`
needs it to look up the same ingestion job `trigger_kb_sync` started.
`wait_for_indexing` sends a Temporal heartbeat on each poll, raises
`RuntimeError` if the job reports `FAILED`, and raises `TimeoutError` if the
job doesn't finish within `timeout` (default 300s).

## API Reference

### `upload_to_s3(file_path, bucket, key_prefix="", s3_client=None) -> str`

Uploads a file to S3 under a UUID-suffixed key, so repeated uploads of the
same filename never collide. Returns the S3 object key.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | `str` | — | Path to the local file to upload |
| `bucket` | `str` | — | Target S3 bucket |
| `key_prefix` | `str` | `""` | Prefix prepended to the generated object key |
| `s3_client` | `boto3 client \| None` | `None` | Override for testing; defaults to `boto3.client("s3")` |

Raises `FileNotFoundError` if `file_path` does not exist.

### `trigger_kb_sync(knowledge_base_id, data_source_id, bedrock_client=None) -> str`

Starts a Bedrock Knowledge Base ingestion job. Returns the ingestion job ID.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge_base_id` | `str` | — | Target Bedrock Knowledge Base ID |
| `data_source_id` | `str` | — | Data source to sync into the knowledge base |
| `bedrock_client` | `boto3 client \| None` | `None` | Override for testing; defaults to `boto3.client("bedrock-agent")` |

### `wait_for_indexing(knowledge_base_id, data_source_id, ingestion_job_id, poll_interval=10.0, timeout=300.0, bedrock_client=None) -> None`

Polls until the ingestion job started by `trigger_kb_sync` completes.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge_base_id` | `str` | — | Same Knowledge Base ID passed to `trigger_kb_sync` |
| `data_source_id` | `str` | — | Must match the `data_source_id` used to start this ingestion job |
| `ingestion_job_id` | `str` | — | Job ID returned by `trigger_kb_sync` |
| `poll_interval` | `float` | `10.0` | Seconds between status checks |
| `timeout` | `float` | `300.0` | Seconds to wait before raising `TimeoutError` |
| `bedrock_client` | `boto3 client \| None` | `None` | Override for testing; defaults to `boto3.client("bedrock-agent")` |

Raises `TimeoutError` if the job does not complete within `timeout`.
