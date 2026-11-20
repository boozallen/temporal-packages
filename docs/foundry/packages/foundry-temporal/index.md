# foundry-temporal

![Status: Available](https://img.shields.io/badge/status-available-brightgreen)
![Version](https://img.shields.io/badge/version-4.0.0-blue)
![Python](https://img.shields.io/badge/python-3.14%20%7C%203.15-blue)

Framework-agnostic building blocks for Temporal workflows and workers:
activity utilities, human-in-the-loop signal and query patterns, retry
policies, an encrypted storage abstraction, observability, and worker
bootstrap. **Depends on:** `foundry-agent-core` (from
[foundry-agent-packages](https://github.com/boozallen/foundry-agent-packages)).

## Install

Install a released wheel from this repo's
[GitHub Releases](https://github.com/boozallen/temporal-packages/releases).
See [Adopting these packages](../../releases/adopting.md) for
the full flow - installing from a release tag for evaluation, or hosting
the wheel in your own index for production, plus verifying the SBOM.

## Quickstart

```python
import hashlib
from datetime import timedelta

from foundry_temporal import HTTP_RETRY_POLICY, HILSignalsMixin, QueryMixin
from temporalio import workflow


@workflow.defn
class ApprovalWorkflow(HILSignalsMixin, QueryMixin):
    def __init__(self):
        super().__init__()

    @workflow.run
    async def run(self, document: str) -> str:
        draft = await workflow.execute_activity(
            "generate_draft",
            document,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=HTTP_RETRY_POLICY,
        )
        # approve_plan must carry the same digest
        self.open_plan_review(hashlib.sha256(draft.encode()).hexdigest())
        await workflow.wait_condition(self.is_plan_decision_received)
        return draft if self.plan_approved else "revise"
```

## What's in the box

| Surface | Highlights |
|---------|------------|
| Activities | `foundry_activity`, `long_running_activity`, `auto_heartbeat`, `BaseActivity`, `BatchActivity`, `HeartbeatActivity` |
| Human-in-the-loop | `HILSignalsMixin`, `QueryMixin`, `create_approval_signal`, `create_feedback_signal` |
| Retry policies | `HTTP_RETRY_POLICY`, `FILE_RETRY_POLICY`, `PROCESSING_RETRY_POLICY`, `DYNAMODB_RETRY_POLICY`, `get_retry_policy_for_activity` |
| Storage | `DocumentMetadata`; `DynamoDBStorage`, `S3Storage`, `LocalFileStorage`, `DocumentStorage` (`foundry_temporal.storage`) |
| Errors | `AgentError`, `StorageError`, `ConfigurationError`, `ValidationError`, `RetryableError`, `NonRetryableError`, `classify_and_wrap_error` |
| Observability | Prometheus metrics and structured logging (`foundry_temporal.observability`), OpenTelemetry tracing (`foundry_temporal.tracing`) |
| Worker | `WorkerConfig`, `create_temporal_client`, `create_worker_with_defaults` (`foundry_temporal.worker`), `bootstrap` |

## Security

- **Explicit TLS posture**: `create_temporal_client()` refuses to connect
  unless `WorkerConfig.tls_mode` is `platform`, `off` (alias for `platform`),
  `tls`, or `mtls`. See the
  [TLS posture guide](../../../../packages/foundry-temporal/docs/tls-posture.md).
- **Storage encrypted at rest**: every storage backend encrypts content with
  AES-256-GCM and requires `FOUNDRY_TEMPORAL_ENCRYPTION_KEY` (64 hex
  characters).
- **Bound approvals**: an approval counts only when its `content_digest`
  matches the content open for review. `approver_id` is not authenticated, so
  restrict who can signal the workflow.
- **Input bounds**: signal comments and injected headers are capped
  (DISA STIG V-222612).

## Reference

- [README](../../../../packages/foundry-temporal/README.md)
- [Changelog](../../../../packages/foundry-temporal/CHANGELOG.md)
- [Source](../../../../packages/foundry-temporal/)
- [License (Apache-2.0)](../../../../LICENSE)
