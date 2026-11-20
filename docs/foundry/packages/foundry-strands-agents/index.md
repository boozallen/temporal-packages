# foundry-strands-agents

![Status: Deprecated](https://img.shields.io/badge/status-deprecated-red)
![Version](https://img.shields.io/badge/version-0.8.0-blue)
![Python](https://img.shields.io/badge/python-3.14%20%7C%203.15-blue)

Temporal activities and clients for calling Strands agents from workflows,
over the A2A JSON-RPC protocol or the Query REST API. **Deprecated:** use
[`foundry-temporal-agents`](../foundry-temporal-agents/index.md) instead.
Importing this package emits a `DeprecationWarning`. **Depends on:**
[`foundry-temporal`](../foundry-temporal/index.md).

## Install

Install a released wheel from this repo's
[GitHub Releases](https://github.com/boozallen/temporal-packages/releases).
See [Adopting these packages](../../releases/adopting.md) for
the full flow - installing from a release tag for evaluation, or hosting
the wheel in your own index for production, plus verifying the SBOM.

## Migrating to `foundry-temporal-agents`

Swap the dependency and the import path; activity names stay the same.

```python
# Before
from foundry_strands_agents import call_strands_agent, call_strands_query

# After
from foundry_temporal_agents import call_strands_agent, call_strands_query
```

- Set `FOUNDRY_AGENT_BEARER_TOKEN` on the worker; it is sent on A2A and Query
  requests.
- `foundry-temporal-agents` does not cap the `StrandsQueryTaskInput` dict
  fields, so bound `context` and `additional_params` before they reach the
  activity.

## What's in the box

| Surface | Highlights |
|---------|------------|
| A2A interface | `call_strands_agent` activity, `strands_agent_activity` decorator, `StrandsAgentClient` |
| Query interface | `call_strands_query` activity, `strands_query_activity` decorator, `StrandsQueryClient` |
| Discovery | `AgentCapabilityChecker`, `AgentRegistry` |
| Retry policies | `STRANDS_AGENT_RETRY_POLICY`, `STRANDS_LONG_OPERATION_RETRY_POLICY`, `get_strands_retry_policy` (`foundry_strands_agents.retry`) |

## Security

- **Bearer authentication on Query only**: Query requests send
  `FOUNDRY_AGENT_QUERY_BEARER_TOKEN`; A2A requests send no bearer token.
- **TLS posture**: the same `FOUNDRY_TLS_*` variables as
  `foundry-temporal-agents`.
- **Input bounds**: `StrandsQueryTaskInput` dict fields are capped by the
  `FOUNDRY_STRANDS_AGENTS_MAX_DICT_*` variables (DISA STIG V-222612).

## Reference

- [README](../../../../packages/foundry-strands-agents/README.md)
- [Changelog](../../../../packages/foundry-strands-agents/CHANGELOG.md)
- [Source](../../../../packages/foundry-strands-agents/)
- [License (Apache-2.0)](../../../../LICENSE)
