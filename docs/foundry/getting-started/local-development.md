# Local Package Development

Use local package source code instead of published versions when developing packages alongside consuming applications.

## Prerequisites

Clone `temporal-packages` alongside your consuming application:

```
~/src/
├── temporal-packages/
│   └── packages/
│       ├── foundry-temporal/
│       └── foundry-doc-ingest/
│       ...  
└── my-app/  # your consuming application
```

Ensure your consuming app has a virtual environment:

```bash
cd my-app
uv venv  # if .venv doesn't exist
```

## Use Local Package

From your consuming application directory:

```bash
uv pip install -e ../temporal-packages/packages/foundry-temporal
```

Changes to the package source are immediately available—no reinstall needed.

## Revert to Published Package

```bash
uv sync
```

This reinstalls dependencies from the lockfile/registry.

> **Note**: `uv sync` requires every dependency to be resolvable from the sources declared in [`pyproject.toml`](../../../pyproject.toml). If you mirror these packages into a package index you host, configure that index (and any authentication it needs) before syncing.

## Check Current State

See which packages are using local source:

```bash
uv pip list --editable
```

## Multiple Packages

```bash
# Use local versions
uv pip install -e ../temporal-packages/packages/foundry-temporal
uv pip install -e ../temporal-packages/packages/foundry-doc-ingest

# Revert all to published
uv sync
```
