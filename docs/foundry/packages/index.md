---
sidebar_position: 1
---

# Packages

Five Foundry packages live under [`packages/`](../../../packages/), each independently versioned.
Each ships its own wheel and CHANGELOG; consumers pick the subset they need.

## `foundry-temporal`

Workflow primitives: activity decorators and base classes, human-in-the-loop
signal and query mixins, retry policies, an encrypted storage abstraction
(DynamoDB, S3, local files), Prometheus metrics and OpenTelemetry tracing,
and worker bootstrap. **Depends on:** `foundry-agent-core` (from
[foundry-agent-packages](https://github.com/boozallen/foundry-agent-packages)).

- [foundry-temporal](./foundry-temporal/index.md)
- [README](../../../packages/foundry-temporal/README.md)
- [CHANGELOG](../../../packages/foundry-temporal/CHANGELOG.md)
- [TLS posture](../../../packages/foundry-temporal/docs/tls-posture.md)

## `foundry-temporal-agents`

Temporal activities and clients for calling Strands agents from workflows,
over the A2A JSON-RPC protocol or the Query REST API, with bearer-token auth,
capability discovery, and agent-specific retry policies. **Depends on:**
`foundry-temporal`.

- [foundry-temporal-agents](./foundry-temporal-agents/index.md)
- [README](../../../packages/foundry-temporal-agents/README.md)
- [CHANGELOG](../../../packages/foundry-temporal-agents/CHANGELOG.md)

## `foundry-doc-ingest`

Document ingestion activities: file validation, local storage, and SQLite
provenance tracking, with no cloud dependencies. **No runtime dependencies on
other packages in this repo.**

- [foundry-doc-ingest](./foundry-doc-ingest/index.md)
- [README](../../../packages/foundry-doc-ingest/README.md)
- [CHANGELOG](../../../packages/foundry-doc-ingest/CHANGELOG.md)

## `foundry-doc-ingest-aws`

AWS integration for document ingestion: S3 upload and Bedrock Knowledge Base
sync activities. **Depends on:** `foundry-doc-ingest`.

- [foundry-doc-ingest-aws](./foundry-doc-ingest-aws/index.md)
- [README](../../../packages/foundry-doc-ingest-aws/README.md)
- [CHANGELOG](../../../packages/foundry-doc-ingest-aws/CHANGELOG.md)

## `foundry-strands-agents` (deprecated)

The predecessor of `foundry-temporal-agents`, kept for existing adopters.
Importing it emits a `DeprecationWarning`; new code should use
`foundry-temporal-agents`. **Depends on:** `foundry-temporal`.

- [foundry-strands-agents](./foundry-strands-agents/index.md)
- [README](../../../packages/foundry-strands-agents/README.md)
- [CHANGELOG](../../../packages/foundry-strands-agents/CHANGELOG.md)

## Dependency graph

```
foundry-agent-core (foundry-agent-packages)
       ↑
foundry-temporal ←── foundry-temporal-agents
       ↑
       └──────────── foundry-strands-agents (deprecated)

foundry-doc-ingest ←── foundry-doc-ingest-aws
```

Every arrow is a hard runtime dependency. `foundry-doc-ingest` is a leaf with
no Foundry dependencies; consumers that only need document ingestion can
install it (and `foundry-doc-ingest-aws`) without pulling in the Temporal
workflow stack. `foundry-temporal` is the only package that reaches outside
this repo, for `foundry-agent-core`.
