# foundry-temporal-agents

![Status: Available](https://img.shields.io/badge/status-available-brightgreen)
![Version](https://img.shields.io/badge/version-0.3.0-blue)
![Python](https://img.shields.io/badge/python-3.14%20%7C%203.15-blue)

Temporal activities and clients for calling Strands agents from workflows,
over the A2A (Agent-to-Agent) JSON-RPC protocol or the Query REST API.
**Depends on:**
[`foundry-temporal`](../foundry-temporal/index.md).

## Install

Install a released wheel from this repo's
[GitHub Releases](https://github.com/boozallen/temporal-packages/releases).
See [Adopting these packages](../../releases/adopting.md) for
the full flow - installing from a release tag for evaluation, or hosting
the wheel in your own index for production, plus verifying the SBOM.

## Quickstart

Register `call_strands_agent` on your worker, then call it by name:

```python
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from foundry_temporal_agents.retry import STRANDS_AGENT_RETRY_POLICY


@workflow.defn
class AgentWorkflow:
    @workflow.run
    async def run(self, agent_url: str, task: str) -> dict:
        result = await workflow.execute_activity(
            "call_strands_agent",
            args=[agent_url, task, {}, None],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=STRANDS_AGENT_RETRY_POLICY,
            heartbeat_timeout=timedelta(seconds=60),
        )
        return {"result": result}
```

## What's in the box

| Surface | Highlights |
|---------|------------|
| A2A interface | `call_strands_agent` activity, `strands_agent_activity` decorator, `StrandsAgentClient` |
| Query interface | `call_strands_query` activity, `strands_query_activity` decorator, `StrandsQueryClient` |
| Dataclass activities | `call_strands_agent_dataclass`, `call_strands_query_dataclass`, and matching decorators |
| Discovery | `AgentCapabilityChecker`, `AgentRegistry` |
| Retry policies | `STRANDS_AGENT_RETRY_POLICY`, `STRANDS_LONG_OPERATION_RETRY_POLICY`, `get_strands_retry_policy` (`foundry_temporal_agents.retry`) |
| Exceptions | `StrandsAgentError` and subclasses, including `AgentAuthenticationError` |

## Security

- **Bearer authentication**: A2A and Query requests send
  `Authorization: Bearer <token>` when `FOUNDRY_AGENT_BEARER_TOKEN` is set.
  A `401`/`403` fails the activity without retrying.
- **TLS posture**: activities build their TLS context from `FOUNDRY_TLS_MODE`
  (`platform` by default, `off` as an alias for `platform`, `tls`, or `mtls`;
  TLS 1.2 minimum). See the README's
  [TLS section](../../../../packages/foundry-temporal-agents/README.md#tls).
- **Capability checks**: when configured, the capability-discovery request is
  sent without the bearer token or TLS context.

## Reference

- [README](../../../../packages/foundry-temporal-agents/README.md)
- [Changelog](../../../../packages/foundry-temporal-agents/CHANGELOG.md)
- [Source](../../../../packages/foundry-temporal-agents/)
- [License (Apache-2.0)](../../../../LICENSE)
