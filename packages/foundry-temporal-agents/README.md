# Foundry Temporal Agents

Temporal integration helpers for calling Strands agents from workflows and activities using both A2A (Agent-to-Agent) JSON-RPC protocol and Query REST API.

## Install

```bash
pip install foundry-temporal-agents
```

From your own package index (see [Adopting these packages](../../docs/foundry/releases/adopting.md)),
or straight from a release tag as the [root README](../../README.md#installation) shows.

## What To Use

### A2A (Agent-to-Agent) Interface
- `call_strands_agent`: ready-to-use Temporal activity for A2A calls
- `strands_agent_activity`: decorator to build custom A2A activities
- `StrandsAgentClient`: direct A2A JSON-RPC client

### Query REST API Interface
- `call_strands_query`: ready-to-use Temporal activity for Query API calls
- `strands_query_activity`: decorator to build custom Query API activities
- `StrandsQueryClient`: direct Query REST API client

### Common Utilities
- `AgentCapabilityChecker` / `AgentRegistry`: capability validation and dynamic agent routing

## A2A Interface Usage

The A2A interface uses JSON-RPC protocol for agent communication.

### Quick Start (Built-in Activity)

```python
from datetime import timedelta
from temporalio import workflow
from temporalio.workflow import execute_activity
from foundry_temporal_agents.retry import STRANDS_AGENT_RETRY_POLICY

@workflow.defn
class MyWorkflow:
    @workflow.run
    async def run(self, input_data: dict) -> dict:
        result = await execute_activity(
            "call_strands_agent",
            args=[
                input_data["agent_url"],
                input_data["task"],
                input_data.get("query_extra_data", {}),
                input_data.get("session_id"),
            ],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=STRANDS_AGENT_RETRY_POLICY,
            heartbeat_timeout=timedelta(seconds=60),
        )
        return {"result": result}
```

### Custom A2A Activity

```python
from datetime import timedelta
from temporalio import workflow
from temporalio.workflow import execute_activity
from foundry_temporal_agents import strands_agent_activity
from foundry_temporal_agents.retry import STRANDS_AGENT_RETRY_POLICY

@strands_agent_activity(
    name="summarize_incident_activity",
    timeout_seconds=600,
    heartbeat_timeout_seconds=60,
    check_capabilities=["text_processing"],
    validate_response=True,
)
async def summarize_incident_activity(title: str, details: str, severity: str) -> dict:
    return {
        "task": f"Summarize incident '{title}' and propose remediations",
        "context": {"details": details, "severity": severity},
        "session_id": f"incident-{title}",
    }
```

### A2A Client Usage

```python
from foundry_temporal_agents import StrandsAgentClient
from foundry_temporal_agents.exceptions import (
    AgentNotFoundError,
    AgentAuthenticationError,
    AgentTimeoutError,
    A2AProtocolError,
)
from foundry_temporal_agents.auth import build_agent_auth_headers

async def run_a2a_call():
    agent_url = "http://agent:8301"
    async with StrandsAgentClient(
        agent_url, timeout=300, max_retries=3, auth_headers=build_agent_auth_headers(agent_url)
    ) as client:
        response = await client.call_agent(
            task="Summarize this incident",
            query_extra_data={"severity": "high", "source": "workflow"},
            session_id="incident-123",
        )
        return response
```

`max_retries=3` suits a call made outside Temporal. Inside a Temporal activity, pass `max_retries=0` so the activity retry policy is the only retry layer, as the built-in activities do.

## Query REST API Interface

The Query interface uses REST HTTP endpoints for structured query processing with search results, document chunks, and confidence scoring.

### Quick Start (Built-in Activity)

```python
from datetime import timedelta
from temporalio import workflow
from temporalio.workflow import execute_activity
from foundry_temporal_agents.retry import STRANDS_AGENT_RETRY_POLICY

@workflow.defn
class QueryWorkflow:
    @workflow.run
    async def run(self, input_data: dict) -> dict:
        result = await execute_activity(
            "call_strands_query",
            args=[
                input_data["agent_url"],
                input_data["query"],
                input_data.get("context", {}),
                input_data.get("session_id"),
                input_data.get("max_results", 10),
                input_data.get("similarity_threshold", 0.7),
            ],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=STRANDS_AGENT_RETRY_POLICY,
            heartbeat_timeout=timedelta(seconds=60),
        )
        return {"query_result": result}
```

### Custom Query Activity

```python
from foundry_temporal_agents import strands_query_activity

@strands_query_activity(
    name="search_documentation",
    timeout_seconds=300,
    heartbeat_timeout_seconds=60,
    validate_response=True,
)
async def search_documentation(topic: str, user_context: dict) -> dict:
    return {
        "query": f"Find documentation about {topic}",
        "context": user_context,
        "max_results": 15,
        "similarity_threshold": 0.8,
    }
```

### Dataclass-Based Activities

Both interfaces support dataclass-based activities following Temporal best practices:

```python
from foundry_temporal_agents import (
    call_strands_agent_dataclass,
    call_strands_query_dataclass,
    StrandsAgentTaskInput,
    StrandsQueryTaskInput
)

# A2A dataclass activity
a2a_input = StrandsAgentTaskInput(
    task="Analyze system logs",
    query_extra_data={"severity": "error"},
    session_id="analysis-session"
)

result = await execute_activity(
    call_strands_agent_dataclass,
    args=[agent_url, a2a_input],
    start_to_close_timeout=timedelta(minutes=5)
)

# Query dataclass activity
query_input = StrandsQueryTaskInput(
    query="What are the main architectural patterns?",
    context={"source": "documentation"},
    max_results=20,
    similarity_threshold=0.9
)

result = await execute_activity(
    call_strands_query_dataclass,
    args=[agent_url, query_input],
    start_to_close_timeout=timedelta(minutes=5)
)
```

### Query Client Usage

```python
from foundry_temporal_agents import StrandsQueryClient
from foundry_temporal_agents.exceptions import AgentNotFoundError, AgentTimeoutError, QueryProcessingError

async def run_query_call():
    async with StrandsQueryClient("http://agent:8000", timeout=300, max_retries=3) as client:
        response = await client.query_agent(
            query="What are the main features of this system?",
            context={"user_id": "123", "source": "web"},
            max_results=15,
            similarity_threshold=0.8
        )

        # Response includes structured data:
        # - response_text: agent's answer
        # - sources: search results that informed the response
        # - chunks_used: specific content chunks used
        # - confidence_score: confidence level (0.0-1.0)
        # - processing_time_ms: processing time

        return response

# Streaming queries
async def stream_query():
    async with StrandsQueryClient("http://agent:8000") as client:
        async for event in client.query_agent_stream("Explain the architecture"):
            if event.get("type") == "token":
                print(event.get("content", ""), end="")
            elif event.get("type") == "done":
                print(f"\nProcessing time: {event.get('processing_time_ms')}ms")
```

As with the A2A client, pass `max_retries=0` when you call `StrandsQueryClient` from inside a Temporal activity.

## Interface Comparison

| Feature | A2A Interface | Query Interface |
|---------|---------------|-----------------|
| Protocol | JSON-RPC | REST HTTP |
| Endpoint | Base agent URL | `/api/v1/query` |
| Response | Flexible (agent-defined) | Structured (sources, chunks, confidence) |
| Streaming | No | Yes (SSE) |
| Use Case | General agent tasks | Document search & analysis |

## Input Length Limits

STIG V-222612 overflow bounds for the user-supplied fields on `StrandsQueryTaskInput` (`query`, `session_id`, `context`, `additional_params`) and `StrandsAgentTaskInput` (`task`, `session_id`, `query_extra_data`, `additional_params`). The same limits apply to the request that a `strands_agent_activity` or `strands_query_activity` function returns. An input above any limit is rejected: `StrandsQueryTaskInput` raises a Pydantic `ValidationError` and `StrandsAgentTaskInput` raises `InputBoundsError`. Inside an activity, a violation raises a non-retryable `ApplicationError` of type `InvalidActivityInput`. Limits are read once at import, so set them before the worker starts.

Defaults mirror the canonical bounds in [`foundry-agent-core`](https://github.com/boozallen/foundry-agent-packages/blob/HEAD/docs/foundry/packages/foundry-agent-core/index.md). The text and dict size defaults are also capped by Temporal transport limits, because each input travels as one Temporal payload, and Temporal rejects a payload above 2 MiB by default. The core defaults alone (2 MiB of text, 4 MiB per dict) would exceed that.

| Environment Variable | Default | Description |
|---|---|---|
| `FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEYS` | `32` | Maximum number of top-level keys in a dict field (core `_MAX_DICT_KEYS`) |
| `FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEY_LEN` | `128` | Maximum length of any dict key (core `_MAX_DICT_KEY_LEN`) |
| `FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_BYTES` | `524288` | Maximum serialized size of a dict field, in bytes (core `_MAX_DICT_BYTES` capped at Temporal's 512 KiB payload warning size) |
| `FOUNDRY_TEMPORAL_AGENTS_MAX_TEXT_LEN` | `524288` | Maximum length of `query` and `task`, in characters (core `_MAX_QUERY_LEN` capped at 512 KiB) |
| `FOUNDRY_TEMPORAL_AGENTS_MAX_SESSION_ID_LEN` | `128` | Maximum length of `session_id`, in characters (core `_MAX_SESSION_ID_LEN`) |
| `FOUNDRY_TEMPORAL_AGENTS_MAX_PAYLOAD_BYTES` | `2031616` | Maximum serialized size of a whole `StrandsQueryTaskInput` or `StrandsAgentTaskInput`, in bytes (Temporal's 2 MiB payload limit minus 64 KiB for the other activity arguments and metadata) |

Sizes are measured the way Temporal's default JSON payload converter serializes the value: compact separators, with non-ASCII characters escaped as `\uXXXX`. One non-ASCII character can therefore count as 6 or 12 bytes, which is why the whole input is also checked against the payload limit.

`query`, `task` and `session_id` must be strings. `session_id` is optional. On the query path, `max_results` must be a whole number from 1 to 100 and `similarity_threshold` 0.0 to 1.0.

Outside an activity, a violation raises `InputBoundsError`, a `ValueError` subclass exported from `foundry_temporal_agents`. `StrandsQueryTaskInput` wraps it in a Pydantic `ValidationError`. If workflow code builds one of these inputs, a violation fails the workflow task, which Temporal retries until the code changes. To fail the workflow instead, list the error types on the worker:

```python
from foundry_temporal_agents import InputBoundsError
from pydantic import ValidationError

worker = Worker(
    client,
    task_queue="agents",
    workflows=[MyWorkflow],
    workflow_failure_exception_types=[InputBoundsError, ValidationError],
)
```

## Authentication

Both interfaces attach a bearer credential to every outbound request when one is configured, using a single shared helper (`build_agent_auth_headers`). Set one of these environment variables on the worker process:

- `FOUNDRY_AGENT_BEARER_TOKEN` — bearer token sent as `Authorization: Bearer <token>` on both A2A and Query requests.
- `FOUNDRY_AGENT_QUERY_BEARER_TOKEN` — back-compat alias from an earlier release; used when `FOUNDRY_AGENT_BEARER_TOKEN` is unset.

If neither variable is set, requests go out with no `Authorization` header and a warning is logged — this is a deployment choice, not an error, since not every agent enforces auth. If the agent rejects a request with `401`/`403`, the request is not retried and the error is not reported as "agent not found". On the A2A path, `StrandsAgentClient` raises `AgentAuthenticationError`, and the activity fails with a non-retryable `ApplicationError` of type `AgentAuthenticationFailure`. On the Query path, `StrandsQueryClient` raises a non-retryable `QueryProcessingError`, and the activity fails with a non-retryable `ApplicationError`.

```python
import os

os.environ["FOUNDRY_AGENT_BEARER_TOKEN"] = "my-shared-secret"
# Both call_strands_agent and call_strands_query now send
# Authorization: Bearer my-shared-secret
```

## TLS

Every activity built with this package's decorators (the built-in
`call_strands_agent` and `call_strands_query`, their dataclass variants, and
your own custom activities) builds its client TLS context from environment
variables on the worker process. A `StrandsAgentClient` or `StrandsQueryClient`
you construct directly uses the `ssl_context` you pass it.


| Variable | Description |
|---|---|
| `FOUNDRY_TLS_MODE` | `platform` (default; TLS is terminated by the platform or mesh), `off` (alias for `platform`), `tls` (verify the agent's server certificate), or `mtls` (also present a client certificate). Any other value raises `ValueError`. |
| `FOUNDRY_TLS_CA_CERTFILE` | Optional CA bundle for `tls`/`mtls` |
| `FOUNDRY_TLS_CLIENT_CERTFILE` | Client certificate; required for `mtls` |
| `FOUNDRY_TLS_CLIENT_KEYFILE` | Client private key; required for `mtls` |

TLS 1.2 is the minimum version for `tls` and `mtls`.

When capability checks are configured on an activity (`check_capabilities`, or
`required_capabilities` from config), the capability-discovery request it sends
to the agent uses neither this TLS context nor the `FOUNDRY_AGENT_BEARER_TOKEN` bearer token.

## Worker Registration

Register the activities you use:

```python
from temporalio.worker import Worker
from foundry_temporal_agents import (
    call_strands_agent,
    call_strands_query,
    call_strands_agent_dataclass,
    call_strands_query_dataclass
)

worker = Worker(
    client,
    task_queue="my-task-queue",
    workflows=[MyWorkflow, QueryWorkflow],
    activities=[
        call_strands_agent,
        call_strands_query,
        call_strands_agent_dataclass,
        call_strands_query_dataclass,
        # Custom activities...
    ],
)
```

## Discovery Helpers

### `AgentCapabilityChecker`

```python
from foundry_temporal_agents.discovery import AgentCapabilityChecker

checker = AgentCapabilityChecker("http://my-agent:8301")
await checker.requires_capability("research")  # raises AgentCapabilityError if unsupported
info = await checker.get_agent_info()
```

### `AgentRegistry` (Dynamic Routing)

```python
from foundry_temporal_agents.discovery import agent_registry

agent_registry.register_agent("research", "http://research-agent:8301")
agent_registry.register_agent("analysis", "http://analysis-agent:8301")

matches = await agent_registry.find_agents_with_capability("research")
selected_url = agent_registry.get_agent_url(matches[0])
```

## Retry Policies

Predefined retry policies work with both interfaces:

```python
from foundry_temporal_agents.retry import (
    STRANDS_AGENT_RETRY_POLICY,
    STRANDS_LONG_OPERATION_RETRY_POLICY,
    get_strands_retry_policy,
)

# Use with any activity
result = await execute_activity(
    "call_strands_query",
    args=[agent_url, query],
    retry_policy=STRANDS_AGENT_RETRY_POLICY,
    start_to_close_timeout=timedelta(minutes=5)
)
```

## Exceptions

Both interfaces use the same exception hierarchy:

```python
from foundry_temporal_agents.exceptions import (
    StrandsAgentError,           # Base exception
    AgentNotFoundError,          # Agent returned 404, or unreachable after retries (status holds the HTTP code, if any)
    AgentAuthenticationError,   # Agent rejected the request as unauthenticated/unauthorized (401/403)
    AgentRequestError,           # Agent rejected the request with another non-retryable 4xx (e.g. 400, 422)
    AgentTimeoutError,           # Request timeout
    A2AProtocolError,           # A2A protocol issues
    QueryProcessingError,       # Query processing issues
    AgentCapabilityError,       # Capability validation
)
```

The activities report a 404 to Temporal as a non-retryable `AgentNotFoundError`. An unreachable agent is reported with the same type but stays retryable. To tell them apart, check the `non_retryable` flag. Do not list `AgentNotFoundError` in `RetryPolicy.non_retryable_error_types`, because that would also stop retries for unreachable agents.

## Testing

```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

## Development

```bash
uv pip install -e .
just test
ruff check src tests
```
