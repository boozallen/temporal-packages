# Temporal Packages

![Python](https://img.shields.io/badge/python-3.14%20%7C%203.15-blue)
![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue)

A uv-workspace monorepo of Python libraries for building [Temporal](https://temporal.io/)
workflows and workers. Each package is independently versioned and installable on its own,
so you take only the pieces you need: workflow primitives (signals, queries, retry
policies, storage abstraction, worker bootstrap), agent integration, and document ingestion
activities, including AWS helpers for S3 upload and Bedrock Knowledge Base sync.

These are libraries, not a runnable service. Starter repos such as
[`temporal-workflow-worker-starter`](https://github.com/boozallen/temporal-workflow-worker-starter)
compose them into a deployable worker.

> **End-to-End Guides** — for a walkthrough of the full Temporal workflow stack, see
> [Getting Started](https://github.com/boozallen/temporal-workflow-worker-starter/blob/HEAD/docs/foundry/guides/end-to-end-how-to-getting-started.md),
> [Next Steps](https://github.com/boozallen/temporal-workflow-worker-starter/blob/HEAD/docs/foundry/guides/end-to-end-how-to-next-steps.md),
> and [Advanced](https://github.com/boozallen/temporal-workflow-worker-starter/blob/HEAD/docs/foundry/guides/end-to-end-how-to-advanced.md).

## Packages

| Package | Description | Version (default branch) |
|---------|-------------|--------------------------|
| [foundry-temporal](packages/foundry-temporal/) | Core Temporal workflow utilities — activities, signals, queries, retry policies, storage abstraction, observability, and worker bootstrap | 4.0.0 |
| [foundry-temporal-agents](packages/foundry-temporal-agents/) | Temporal integration helpers for calling Strands agents from workflows via the A2A protocol | 0.4.0 |
| [foundry-doc-ingest](packages/foundry-doc-ingest/) | Document ingestion activities for Temporal workflows — file validation, local storage, provenance tracking | 0.2.0 |
| [foundry-doc-ingest-aws](packages/foundry-doc-ingest-aws/) | AWS integration for document ingestion — S3 upload and Bedrock Knowledge Base sync | 0.2.0 |

All packages support Python 3.14 and 3.15.

## Installation

Each package installs directly from this repository. Install only what you need.
Releases are tagged per package, as `<package>/v<version>`; see this repo's tags
(`git tag --list` or the [GitHub Releases page](https://github.com/boozallen/temporal-packages/releases)) for the current version of each package.

```bash
# foundry-temporal (needs foundry-agent-core from foundry-agent-packages)
pip install \
  "foundry-agent-core @ git+https://github.com/boozallen/foundry-agent-packages@foundry-agent-core/v1.4.0#subdirectory=packages/foundry-agent-core" \
  "foundry-temporal @ git+https://github.com/boozallen/temporal-packages@foundry-temporal/v4.0.0#subdirectory=packages/foundry-temporal"

# foundry-temporal-agents (needs foundry-temporal and foundry-agent-core)
pip install \
  "foundry-agent-core @ git+https://github.com/boozallen/foundry-agent-packages@foundry-agent-core/v1.4.0#subdirectory=packages/foundry-agent-core" \
  "foundry-temporal @ git+https://github.com/boozallen/temporal-packages@foundry-temporal/v4.0.0#subdirectory=packages/foundry-temporal" \
  "foundry-temporal-agents @ git+https://github.com/boozallen/temporal-packages@foundry-temporal-agents/v0.4.0#subdirectory=packages/foundry-temporal-agents"

# foundry-doc-ingest
pip install "foundry-doc-ingest @ git+https://github.com/boozallen/temporal-packages@foundry-doc-ingest/v0.2.0#subdirectory=packages/foundry-doc-ingest"

# foundry-doc-ingest-aws (needs foundry-doc-ingest)
pip install \
  "foundry-doc-ingest @ git+https://github.com/boozallen/temporal-packages@foundry-doc-ingest/v0.2.0#subdirectory=packages/foundry-doc-ingest" \
  "foundry-doc-ingest-aws @ git+https://github.com/boozallen/temporal-packages@foundry-doc-ingest-aws/v0.2.0#subdirectory=packages/foundry-doc-ingest-aws"
```

There is no public package index for these packages, so pip cannot find a sibling
package by name unless you host the wheels in your own index (see
[Adopting these packages](docs/foundry/releases/adopting.md)). Each command lists
the siblings it needs.

The `foundry-temporal/v4.0.0` and `foundry-temporal-agents/v0.4.0` releases
support Python 3.14 and 3.15.

These examples pin the latest release of each package when this README was
last updated. A package's own README describes the code on the default
branch, which can be newer than the release pinned here.

With `uv`, add them to your `pyproject.toml`:

```toml
[project]
dependencies = [
    "foundry-temporal",
    "foundry-agent-core",
]

[tool.uv.sources]
foundry-temporal = { git = "https://github.com/boozallen/temporal-packages", subdirectory = "packages/foundry-temporal", tag = "foundry-temporal/v4.0.0" }
foundry-agent-core = { git = "https://github.com/boozallen/foundry-agent-packages", subdirectory = "packages/foundry-agent-core", tag = "foundry-agent-core/v1.4.0" }
```

`foundry-temporal` depends on `foundry-agent-core` 1.4.0, which lives in the
companion [foundry-agent-packages](https://github.com/boozallen/foundry-agent-packages)
repository. uv only applies a source to a direct dependency, so list
`foundry-agent-core` in `dependencies` and pin its tag.

**Intended adoption pattern:** installing straight from `github.com` is fine for
evaluation, demos, and POCs. For production, build the wheels and mirror them into a
package index you control (Artifactory, AWS CodeArtifact, Sonatype Nexus, GitLab Package
Registry, etc.), then repoint your dependency specs at that index. Build a wheel with
`just build <package>`.

## Getting Started

`foundry-temporal` provides the workflow primitives. Mixins add human-in-the-loop signals
and query handlers to a workflow definition:

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
        draft = await self._create_draft(document)

        # Open the review with the draft's digest, then block until a human
        # approves it (approve_plan with the same digest) or sends feedback
        self.open_plan_review(hashlib.sha256(draft.encode()).hexdigest())
        await workflow.wait_condition(self.is_plan_decision_received)

        if self.plan_approved:
            return await self._finalize_document(draft)
        return await self._revise_draft(draft, self.plan_feedback_comments)
```

Pre-built retry policies cover the common failure shapes, so activities do not each
hand-roll backoff. Temporal applies a retry policy where the workflow schedules the
activity:

```python
from datetime import timedelta

from foundry_temporal import HTTP_RETRY_POLICY
from temporalio import activity, workflow


@activity.defn
async def call_external_api() -> dict:
    ...


# Inside a workflow's run method: retries with exponential backoff on transient
# HTTP errors (5xx, timeouts).
result = await workflow.execute_activity(
    call_external_api,
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=HTTP_RETRY_POLICY,
)
```

Each package's README covers its own API surface in full — start with
[`packages/foundry-temporal/README.md`](packages/foundry-temporal/README.md).

## Local Development & Verification

Working on the packages themselves, or verifying the repo before you depend on it.

**Prerequisites**

- Python 3.14 or 3.15
- [uv](https://docs.astral.sh/uv/) package manager
- [just](https://github.com/casey/just) command runner

**Setup**

```bash
git clone https://github.com/boozallen/temporal-packages.git
cd temporal-packages
just setup          # uv sync --all-packages --all-groups
```

**Verify**

```bash
just check          # full gate: lint + format + type-check + test
just test           # every package's suite (unit + integration tiers)
just ci             # alias for the full gate; run before opening a PR
```

No credentials or running Temporal server is required. `just setup` does need network
access, because the workspace resolves `foundry-agent-core` (from the companion
[foundry-agent-packages](https://github.com/boozallen/foundry-agent-packages) repository)
as a published, hash-locked release rather than from a local checkout. The root
[`pyproject.toml`](pyproject.toml) and [`uv.lock`](uv.lock) say where that release comes from.

**Narrower loops**

| Command | Description |
|---------|-------------|
| `just sync` | Sync the workspace venv with the lockfile |
| `just lint` / `just lint-fix` | Ruff lint plus the bandit command-injection sink set / auto-fix |
| `just format` / `just format-fix` | Check / apply formatting |
| `just type-check` | basedpyright type checking |
| `just test-unit` / `just test-integration` | One tier only; 0 collected integration tests reports as SKIP |
| `just test-pkg <pkg>` | One package's full suite |
| `just check-pkg <pkg>` | The full gate scoped to one package |
| `just lint-pkg <pkg>` / `just format-pkg <pkg>` / `just type-check-pkg <pkg>` | Individual gates, one package |
| `just build <pkg>` / `just build-all` | Build wheels |
| `just clean` | Remove build artifacts and tooling caches |

`just --list` shows the full recipe surface.

The unit/integration split is by **directory**, not by marker: every package has
`tests/unit/` and `tests/integration/`, and a test's tier is decided by where the file
lives, so the classification cannot be forgotten. No recipe passes `-m`. Markers are
retained only for cross-cutting traits (`slow`, `network`, `aws`, `temporal`) that a
directory cannot express. `conftest.py` stays at the `tests/` root so its fixtures are
visible to both tiers.

`just test` / `test-unit` / `test-integration` share one internal `_test-loop` recipe,
parameterized by the test directory, that runs pytest once per package from the workspace
root (never a single glob across `packages/*/tests`), so each package's own
pytest/coverage config is honored and the run prints a real per-package pass/fail/count
summary. Each package also has its own local `justfile`, so `just test` run from inside
`packages/<pkg>/` tests only that package.

HTML coverage is always on, via each package's `--cov-report=html:htmlcov/<module>`
addopt, so a per-package report lands in `htmlcov/<module>/index.html` without a separate
recipe.

## Version Management

Each package's version lives in its own `pyproject.toml` — the single source of truth.

```bash
just version foundry-temporal              # show
just version-patch foundry-temporal        # 2.0.0 → 2.0.1
just version-minor foundry-temporal        # 2.0.0 → 2.1.0
just version-major foundry-temporal        # 2.0.0 → 3.0.0
just version-set foundry-temporal 2.0.0    # explicit
```

## Documentation

| Document | Description |
|----------|-------------|
| [Overview](docs/foundry/index.md) | Package map, dependency graph, testing posture |
| [Packages](docs/foundry/packages/index.md) | One page per package: install, quickstart, API surface, security notes |
| [Adopting these packages](docs/foundry/releases/adopting.md) | Consuming release wheels: hosting them in your own index, pinning, verifying the SBOM |
| [Local Development](docs/foundry/getting-started/local-development.md) | Developing against local package source |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Fork workflow, dev setup, review and merge process |
| [SECURITY.md](SECURITY.md) | Reporting a vulnerability |

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
