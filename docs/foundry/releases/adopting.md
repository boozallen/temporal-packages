---
sidebar_position: 1
---

# Adopting these packages

`temporal-packages` ships releases as **GitHub Releases**. Each release
attaches one package's wheel, its source distribution, and a Syft SBOM.
There is no public PyPI mirror yet — host the wheel in your own index
and point `uv` / `pip` at it.

This page covers the adopter-facing flow: download the artifacts, host them,
consume them.

## 1. Find the release

Each tagged release on this repo's
[Releases page](https://github.com/boozallen/temporal-packages/releases)
covers one package and includes:

- **Wheel:** `foundry_<name>-<version>-py3-none-any.whl` (for example `foundry_temporal-4.0.0-py3-none-any.whl`)
- **Source distribution:** `foundry_<name>-<version>.tar.gz`
- **SBOM:** `sbom-*.cyclonedx.json`

Tags follow the per-package version in each package's `pyproject.toml`, in
the form `<package>/v<version>`. A typical tag is `foundry-temporal/v4.0.0`. Releases never re-publish an
existing version — every tag is monotonic per package.

[`foundry-temporal`](../packages/foundry-temporal/index.md) depends on `foundry-agent-core`, which is released from
[foundry-agent-packages](https://github.com/boozallen/foundry-agent-packages/releases).
Host that wheel too.

## 2. Host the wheels in your own index

The wheels are vanilla PEP 427 artifacts; any tool that serves a PyPI-compatible
index works. Common patterns:

- **JFrog Artifactory** — create a *local PyPI* repo and upload the wheel files.
- **AWS CodeArtifact** — `aws codeartifact publish-package-version` per wheel.
- **`devpi` / `pypiserver` / nginx auto-index** — point them at a local mirror
  directory you populate from `gh release download`.

The supported pattern is "fetch the wheel, host it on your side, pin against
your index". We do not maintain mirror metadata, sign release artifacts, or
guarantee URL stability for old releases.

## 3. Consume from your project

```toml
# pyproject.toml in the downstream worker
[project]
name = "my-worker"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = []

[[tool.uv.index]]
name = "my-index"
url = "https://<your-index>/simple"
explicit = true

[tool.uv.sources]
foundry-agent-core = { index = "my-index" }
foundry-temporal = { index = "my-index" }
foundry-temporal-agents = { index = "my-index" }
```

```bash
# uv applies a source only to a direct dependency, so list foundry-agent-core too
uv add foundry-agent-core foundry-temporal foundry-temporal-agents
```

To evaluate without an index, install from the release tags, listing every
package the install needs:

```bash
pip install \
  "foundry-agent-core @ git+https://github.com/boozallen/foundry-agent-packages@foundry-agent-core/v<version>#subdirectory=packages/foundry-agent-core" \
  "foundry-temporal @ git+https://github.com/boozallen/temporal-packages@foundry-temporal/v<version>#subdirectory=packages/foundry-temporal"
```

## 4. Verify what you're installing

Every wheel ships with an SBOM as a separate release asset. It is a scan of
the package's source directory, so it does not list resolved dependencies.
Before promoting a release to a production index:

1. `gh release download foundry-temporal/v4.0.0 --repo https://github.com/boozallen/temporal-packages --pattern 'sbom-*'`
2. Generate an SBOM of the environment you install the wheels into (for
   example, `syft dir:.venv -o cyclonedx-json`) and confirm the dependency set
   matches what your supply-chain policy allows.
3. Scan it with your own tooling (for example, `grype sbom:<sbom-file>`) for
   unresolved CVEs above your tolerance threshold. Releases do not attach a
   vulnerability scan report.

## 5. Stay current

- **Watch the repo** for releases — GitHub will email new tags to watchers.
- **Pin against your own index**, not against `develop` or any moving ref
  here. Pre-release builds (`rcN`) are not published as GitHub Releases.
- **Read the relevant package CHANGELOG** at upgrade time. The root
  [`CHANGELOG.md`](../../../CHANGELOG.md)
  cross-references each package's per-package changelog under
  `packages/<package>/CHANGELOG.md`.

## When to file an issue

- The wheel installs but imports fail → file an issue with the `pip`/`uv`
  resolution output and the Python version
- The SBOM asset is missing for a release → file an issue
- A CVE you care about is unresolved in your scan → file an issue with the
  CVE ID, the affected package version, and your remediation deadline

Security advisories should go through the private flow described in
[`SECURITY.md`](../../../SECURITY.md),
not the public issue tracker.
