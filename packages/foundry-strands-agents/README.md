# Foundry Strands Agents

Temporal integration helpers for calling Strands agents from workflows and activities using both A2A (Agent-to-Agent) JSON-RPC protocol and Query REST API.

## Deprecated

This package is deprecated. Use
[`foundry-temporal-agents`](../foundry-temporal-agents/) instead. Importing
this package emits a warning:

```bash
python -c "import foundry_strands_agents"
```

Expected: `DeprecationWarning: foundry-strands-agents is deprecated. Use
foundry-temporal-agents (import foundry_temporal_agents) instead.`

## Install

```bash
pip install foundry-strands-agents
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
from foundry_strands_agents.retry import STRANDS_AGENT_RETRY_POLICY

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
from foundry_strands_agents import strands_agent_activity
from foundry_strands_agents.retry import STRANDS_AGENT_RETRY_POLICY

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
from foundry_strands_agents import StrandsAgentClient
from foundry_strands_agents.exceptions import AgentNotFoundError, AgentTimeoutError, A2AProtocolError

async def run_a2a_call():
    async with StrandsAgentClient("http://agent:8301", timeout=300, max_retries=3) as client:
        response = await client.call_agent(
            task="Summarize this incident",
            query_extra_data={"severity": "high", "source": "workflow"},
            session_id="incident-123",
        )
        return response
```

## Query REST API Interface

The Query interface uses REST HTTP endpoints for structured query processing with search results, document chunks, and confidence scoring.

### Quick Start (Built-in Activity)

```python
from datetime import timedelta
from temporalio import workflow
from temporalio.workflow import execute_activity
from foundry_strands_agents.retry import STRANDS_AGENT_RETRY_POLICY

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
from foundry_strands_agents import strands_query_activity

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
from foundry_strands_agents import (
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
from foundry_strands_agents import StrandsQueryClient
from foundry_strands_agents.exceptions import AgentNotFoundError, AgentTimeoutError, QueryProcessingError

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

## Interface Comparison

| Feature | A2A Interface | Query Interface |
|---------|---------------|-----------------|
| Protocol | JSON-RPC | REST HTTP |
| Endpoint | Base agent URL | `/api/v1/query` |
| Response | Flexible (agent-defined) | Structured (sources, chunks, confidence) |
| Streaming | No | Yes (SSE) |
| Use Case | General agent tasks | Document search & analysis |

## Input Length Limits

STIG V-222612 overflow bounds for `StrandsQueryTaskInput` dict fields (`context`, `additional_params`):

| Variable | Default | Description |
|---|---|---|
| `FOUNDRY_STRANDS_AGENTS_MAX_DICT_KEYS` | `32` | Maximum number of top-level keys in a dict field |
| `FOUNDRY_STRANDS_AGENTS_MAX_DICT_KEY_LEN` | `128` | Maximum length of any dict key |
| `FOUNDRY_STRANDS_AGENTS_MAX_DICT_BYTES` | `16384` | Maximum serialized size of a dict field (bytes) |

## Worker Registration

Register the activities you use:

```python
from temporalio.worker import Worker
from foundry_strands_agents import (
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
from foundry_strands_agents.discovery import AgentCapabilityChecker

checker = AgentCapabilityChecker("http://my-agent:8301")
await checker.requires_capability("research")  # raises AgentCapabilityError if unsupported
info = await checker.get_agent_info()
```

### `AgentRegistry` (Dynamic Routing)

```python
from foundry_strands_agents.discovery import agent_registry

agent_registry.register_agent("research", "http://research-agent:8301")
agent_registry.register_agent("analysis", "http://analysis-agent:8301")

matches = await agent_registry.find_agents_with_capability("research")
selected_url = agent_registry.get_agent_url(matches[0])
```

## Retry Policies

Predefined retry policies work with both interfaces:

```python
from foundry_strands_agents.retry import (
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
from foundry_strands_agents.exceptions import (
    StrandsAgentError,           # Base exception
    AgentNotFoundError,          # Agent unreachable
    AgentTimeoutError,           # Request timeout
    A2AProtocolError,           # A2A protocol issues
    QueryProcessingError,       # Query processing issues
    AgentCapabilityError,       # Capability validation
)
```

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
