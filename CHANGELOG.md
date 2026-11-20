# Changelog

Cross-package summary of changes across the `temporal-packages` monorepo.
For per-package detail see each package's own `CHANGELOG.md`:

- [foundry-temporal](packages/foundry-temporal/CHANGELOG.md)
- [foundry-temporal-agents](packages/foundry-temporal-agents/CHANGELOG.md)
- [foundry-doc-ingest](packages/foundry-doc-ingest/CHANGELOG.md)
- [foundry-doc-ingest-aws](packages/foundry-doc-ingest-aws/CHANGELOG.md)
- [foundry-strands-agents](packages/foundry-strands-agents/CHANGELOG.md) (deprecated)

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Per-package versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-11-05

### Changed

- foundry-strands-agents: 0.8.0 to 0.8.1
- foundry-temporal-agents: 0.3.0 to 0.4.0

## [1.0.0] - 2026-10-19

### Changed

- foundry-temporal: 3.2.0 to 4.0.0

## [0.2.0] - 2026-10-19

### Changed

- foundry-doc-ingest: 0.1.0 to 0.2.0
- foundry-doc-ingest-aws: 0.1.0 to 0.2.0
- foundry-strands-agents: 0.7.0 to 0.8.0
- foundry-temporal: 3.1.0 to 3.2.0
- foundry-temporal-agents: 0.2.0 to 0.3.0

## [0.1.0] - 2026-10-08

### Changed

- foundry-strands-agents: 0.6.1 to 0.7.0
- foundry-temporal: 3.0.0 to 3.1.0
- foundry-temporal-agents: 0.1.0 to 0.2.0

### Removed

Both removals shipped in the 2026-09-25 release, before this section's version.

- Removed `foundry-auth` from this repo. It has no real Temporal coupling and
  has moved to
  [foundry-agent-packages](https://github.com/boozallen/foundry-agent-packages).
  Already-published wheels remain resolvable on the Github registry for pinned
  consumers; new installs should target foundry-agent-packages.
- Removed `foundry-aws-utilities` from this repo. It has no real Temporal
  coupling and has moved to
  [foundry-agent-packages](https://github.com/boozallen/foundry-agent-packages).
  Already-published wheels remain resolvable on the Github registry for pinned
  consumers; new installs should target foundry-agent-packages.

