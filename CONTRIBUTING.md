# Contributing to Temporal Packages

Thank you for your interest in contributing! This guide covers how to get started,
submit changes, and what to expect during review.

## Code of Conduct

All participants are expected to treat others with respect and professionalism.
Harassment or abusive behavior will not be tolerated.

## Getting Started

### Fork and Clone

1. Fork this repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/temporal-packages.git
   cd temporal-packages
   ```
3. Add the upstream remote:
   ```bash
   git remote add upstream https://github.com/boozallen/temporal-packages.git
   ```

### Development Setup

This is a Python monorepo managed with [uv](https://docs.astral.sh/uv/) and
[just](https://github.com/casey/just). You need Python 3.14 or 3.15.

Install all dependencies:

```bash
just setup          # uv sync --all-packages --all-groups
```

Verify your setup:

```bash
just check
```

No credentials are required. `just setup` does need network access, because the workspace
resolves `foundry-agent-core` (from the companion
[foundry-agent-packages](https://github.com/boozallen/foundry-agent-packages)
repository) as a published, hash-locked release rather than from a local checkout. The root
[`pyproject.toml`](pyproject.toml) and [`uv.lock`](uv.lock) say where that release comes from.

### Common Commands

| Command | Description |
|---------|-------------|
| `just sync` | Sync the workspace venv with the lockfile |
| `just setup` | Set up the local development environment |
| `just lint` | Ruff lint + the bandit command-injection sink set across all packages |
| `just lint-fix` | Auto-fix ruff lint findings |
| `just format` / `just format-fix` | Check / apply formatting |
| `just type-check` | basedpyright type checking |
| `just check` | Full gate: `lint` + `format` + `type-check` + `test` |
| `just ci` | Alias for the full gate; run before opening a PR |
| `just test` | Every package's suite, both tiers |
| `just test-unit` / `just test-integration` | One tier only |
| `just test-pkg <pkg>` | One package's full suite |
| `just check-pkg <pkg>` | The full gate scoped to one package |
| `just lint-pkg <pkg>` / `just format-pkg <pkg>` / `just type-check-pkg <pkg>` | Individual gates, one package |
| `just build <pkg>` / `just build-all` | Build wheels |
| `just clean` | Remove build artifacts and tooling caches |

`just --list` shows the full recipe surface.

### Testing Conventions

- New tests go in `tests/unit/` unless they need external services or credentials, in
  which case they go in `tests/integration/`. The tier is decided by the **directory**,
  not by a marker, so the classification cannot be forgotten.
- Packages with zero integration tests report as SKIP, not a failure.
- Shared fixtures live in `tests/conftest.py` so both tiers see them; a test that needs
  one takes it as a fixture rather than importing `tests.conftest`.
- Do not add `tests/__init__.py` — test module basenames may repeat across packages
  because every `addopts` carries `--import-mode=importlib`.
- Markers are retained only for cross-cutting traits (`slow`, `network`, `aws`,
  `temporal`) that a directory cannot express.
- HTML coverage is always on, via each package's `--cov-report=html:htmlcov/<module>`
  addopt, so a per-package report lands in `htmlcov/<module>/index.html`. There is no
  separate coverage recipe.
- `just lint` runs ruff plus the narrow bandit command-injection sink set
  (`B602,B603,B605,B607`), both at the root and from inside any `packages/<pkg>/`, where
  bandit reads `[tool.bandit]` from the workspace-root `pyproject.toml`.

## Making Changes

### Branch Workflow

1. Sync your fork with upstream:
   ```bash
   git fetch upstream
   git checkout develop
   git merge upstream/develop
   ```
2. Create a feature branch from `develop`:
   ```bash
   git checkout -b feature/your-change
   ```
3. Make your changes, keeping commits focused (one logical change per commit)
4. Push to your fork:
   ```bash
   git push origin feature/your-change
   ```

### Branch Naming

- `feature/<short-description>` for new features
- `fix/<short-description>` for bug fixes
- `docs/<short-description>` for documentation-only changes

### PR Conventions

- All PRs target the `develop` branch
- Keep changes focused and small
- Include a clear description of what changed and why
- Reference any related issues
- Add or update tests for behavioral changes
- Update docs when behavior or interfaces change
- Bump the version only for the packages you are releasing; each package's version
  lives in its own `pyproject.toml`
- Ensure `just check` passes locally before requesting review

## Submitting a Pull Request

1. Open a pull request from your fork's branch to `upstream/develop`
2. Fill out the PR template checklist
3. A maintainer will review your PR — only designated maintainers have merge rights

### What to Expect

- Maintainers review all PRs before merging (role-based permissions)
- You may be asked to make changes; push additional commits to your branch
- Once approved, a maintainer will merge your PR
- External contributors do not have direct push or merge access

## Review and Merge Process

This project uses a maintainer-controlled merge model:

- Only designated maintainers (defined in [`.github/CODEOWNERS`](.github/CODEOWNERS))
  can merge pull requests
- At least two approving reviews are required
- At least one CODEOWNERS review is required
- Stale approvals are dismissed when new commits are pushed
- No bypass is allowed — maintainers follow the same review process

## Reporting Security Issues

**Do not report security vulnerabilities through public GitHub issues.**

See [SECURITY.md](SECURITY.md) for instructions on reporting vulnerabilities privately.

## Questions

Open an issue or start a discussion for help with contributions, release flow, or
package onboarding.

## License

By contributing, you agree that your contributions will be licensed under the same
license as this project. See [LICENSE](LICENSE) for details.
