# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Foundry Strands Agents - Temporal integration for Strands agents.

This package provides Temporal activities and clients for interacting with Strands agents
using both the A2A (Agent-to-Agent) JSON-RPC protocol and the Query REST API.
"""

# ruff: noqa: E402

import warnings
from importlib.metadata import PackageNotFoundError, version

warnings.warn(
    "foundry-strands-agents is deprecated. Use foundry-temporal-agents (import foundry_temporal_agents) instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .activities import (
    call_strands_agent,
    call_strands_agent_dataclass,
    strands_agent_activity,
    strands_agent_dataclass_activity,
)
from .client import StrandsAgentClient
from .discovery import AgentCapabilityChecker, AgentRegistry, agent_registry
from .exceptions import (
    A2AProtocolError,
    AgentCapabilityError,
    AgentNotFoundError,
    AgentTimeoutError,
    QueryProcessingError,
    StrandsAgentError,
)
from .models import StrandsAgentTaskInput
from .protocols import A2AMessageBuilder, extract_agent_response, validate_a2a_response
from .query_activities import (
    call_strands_query,
    call_strands_query_dataclass,
    strands_query_activity,
    strands_query_dataclass_activity,
)
from .query_client import StrandsQueryClient
from .query_models import StrandsQueryTaskInput

try:
    __version__ = version("foundry-strands-agents")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

__all__ = [
    "__version__",
    # A2A activities
    "call_strands_agent",
    "call_strands_agent_dataclass",
    # Query activities
    "call_strands_query",
    "call_strands_query_dataclass",
    # Decorators
    "strands_agent_activity",
    "strands_agent_dataclass_activity",
    "strands_query_activity",
    "strands_query_dataclass_activity",
    # Clients
    "StrandsAgentClient",
    "StrandsQueryClient",
    # Models
    "StrandsAgentTaskInput",
    "StrandsQueryTaskInput",
    # Discovery
    "AgentCapabilityChecker",
    "AgentRegistry",
    "agent_registry",
    # Exceptions
    "StrandsAgentError",
    "AgentNotFoundError",
    "AgentTimeoutError",
    "A2AProtocolError",
    "AgentCapabilityError",
    "QueryProcessingError",
    # Protocols
    "A2AMessageBuilder",
    "extract_agent_response",
    "validate_a2a_response",
]
