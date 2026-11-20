---
sidebar_position: 1
---

# Overview

Python libraries for building [Temporal](https://temporal.io/) workflows and workers.

`temporal-packages` is a uv-workspace monorepo. Each package is independently
versioned and installable on its own, so a consuming worker takes only the pieces it
needs. These are libraries, not a runnable service — starter repos such as
[`temporal-workflow-worker-starter`](https://github.com/boozallen/temporal-workflow-worker-starter)
compose them into something deployable.

## Packages

| Package | Purpose | Depends on |
|---------|---------|------------|
| [`foundry-temporal`](./packages/foundry-temporal/index.md) | Workflow primitives — activities, signals, queries, retry policies, storage abstraction, observability, worker bootstrap | [`foundry-agent-core`](https://github.com/boozallen/foundry-agent-packages/blob/HEAD/docs/foundry/packages/foundry-agent-core/index.md) |
| [`foundry-temporal-agents`](./packages/foundry-temporal-agents/index.md) | Calling Strands agents from workflows over the A2A protocol | `foundry-temporal` |
| [`foundry-doc-ingest`](./packages/foundry-doc-ingest/index.md) | Document ingestion activities — file validation, local storage, provenance tracking | _(none)_ |
| [`foundry-doc-ingest-aws`](./packages/foundry-doc-ingest-aws/index.md) | AWS integration for document ingestion — S3 upload, Bedrock Knowledge Base sync | `foundry-doc-ingest` |

## Testing posture

The unit/integration split is by **directory**, not by marker: every package has
`tests/unit/` and `tests/integration/`, and a test's tier is decided by where the file
lives, so the classification cannot be forgotten. No recipe passes `-m`. Markers are
retained only for cross-cutting traits (`slow`, `network`, `aws`, `temporal`) that a
directory cannot express.

`just lint` runs Ruff plus a narrow `bandit -t B602,B603,B605,B607` command-injection
sink set, both at the workspace root and from inside any `packages/<pkg>/`.

## Where to go next

- **[Packages](./packages/index.md)** — summary of each package, its dependencies, and a link to its page
- **[Adopting these packages](./releases/adopting.md)** — how to consume the wheels from a downstream repo
- **[Local development](./getting-started/local-development.md)** — developing against local package source from a consuming application
- **[Contributing](../../CONTRIBUTING.md)** — fork workflow, dev setup, review and merge process
- **[Security](../../SECURITY.md)** — reporting a vulnerability
