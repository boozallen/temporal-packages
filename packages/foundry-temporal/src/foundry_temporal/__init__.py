# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Foundry Temporal - Core Temporal workflow utilities (framework-agnostic)

This package provides reusable baseline components for building Temporal-based workflows
with any agent framework. It is completely independent of specific agent implementations.

Key Features:
- Human-in-loop signal patterns (approve/feedback/revise cycles)
- Retry policy configurations for different activity types
- Storage abstraction supporting multiple backends
- Observability integration (Prometheus + structlog)
- Generic workflow state management
- Framework-agnostic activity utilities

Usage Patterns:

    # Use HIL patterns for human approval workflows
    from foundry_temporal import HILSignalsMixin, QueryMixin

    @workflow.defn
    class MyWorkflow(HILSignalsMixin, QueryMixin):
        def __init__(self):
            super().__init__()

    # Use retry policies for robust activities
    from foundry_temporal import HTTP_RETRY_POLICY

    @activity.defn(retry_policy=HTTP_RETRY_POLICY)
    async def call_external_api():
        pass

    # Use activity utilities for standard patterns
    from foundry_temporal import foundry_activity, ActivityConfig

    @foundry_activity(config=ActivityConfig(enable_observability=True))
    async def my_activity(param: str) -> str:
        return f"processed: {param}"

    # Use storage abstraction
    from foundry_temporal.storage import DocumentStorage
    from foundry_temporal.models import DocumentMetadata

Agent Integration:
    For specific agent frameworks, use their dedicated packages:
    - foundry_strands_agents - For Strands agent integration
"""

__author__ = "Foundry Baseline Team"
__description__ = "Core Temporal workflow utilities (framework-agnostic)"

from importlib.metadata import PackageNotFoundError, version

# Activity utilities for standard patterns
from .activities import (
    ActivityConfig,
    BaseActivity,
    BatchActivity,
    HeartbeatActivity,
    auto_heartbeat,
    create_heartbeat_activity,
    create_simple_activity,
    foundry_activity,
    long_running_activity,
)

# Composition-root helpers for a worker's own bootstrap.py
from .bootstrap import Registrations, bootstrap

# Dataclass-based activity patterns (best practice)
from .dataclass_activities import (
    APICallInput,
    BasicTaskInput,
    BatchProcessingInput,
    FileProcessingInput,
    dataclass_activity,
    dataclass_to_dict,
    dict_to_dataclass,
    validate_dataclass_input,
)

# Error types and classification utilities
from .errors import (
    AgentError,
    ConfigurationError,
    NonRetryableError,
    RetryableError,
    StorageError,
    ValidationError,
    WorkflowError,
    classify_and_wrap_error,
    create_non_retryable_error,
    create_retryable_error,
    is_retryable_error,
)

# Header injection for client-side header attachment
from .header_injection import (
    HeaderInjectionInterceptor,
    outbound_headers,
)

# Header propagation for passing context through workflows
from .header_propagation import (
    HeaderPropagationInterceptor,
    get_header,
    get_propagated_headers,
)

# Infrastructure models (separate from template-specific models in team code)
from .models import (
    DocumentMetadata,  # For storage.py infrastructure
)

# Observability utilities are NOT eagerly imported here to avoid pulling
# prometheus_client into Temporal's workflow sandbox (which restricts urllib.request).
# Use `from foundry_temporal.observability import ...` directly when needed
# in activity code or worker setup — never inside workflow definitions.
# Query patterns for workflow status
from .queries import (
    QueryMixin,
)
from .retry_policies import (
    DYNAMODB_RETRY_POLICY,
    FILE_RETRY_POLICY,
    HTTP_RETRY_POLICY,
    PROCESSING_RETRY_POLICY,
    get_retry_policy_for_activity,
)

# Signal patterns for human-in-the-loop workflows
from .signals import (
    HILSignalsMixin,
    create_approval_signal,
    create_feedback_signal,
    open_approval_review,
)

try:
    __version__ = version("foundry-temporal")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

__all__ = [
    "__version__",
    # Activity utilities
    "ActivityConfig",
    "BaseActivity",
    "BatchActivity",
    "HeartbeatActivity",
    "auto_heartbeat",
    "foundry_activity",
    "long_running_activity",
    "create_simple_activity",
    "create_heartbeat_activity",
    # Composition root
    "Registrations",
    "bootstrap",
    # Dataclass-based activity patterns (best practice)
    "dataclass_activity",
    "BasicTaskInput",
    "FileProcessingInput",
    "BatchProcessingInput",
    "APICallInput",
    "dataclass_to_dict",
    "dict_to_dataclass",
    "validate_dataclass_input",
    # Retry policies
    "FILE_RETRY_POLICY",
    "PROCESSING_RETRY_POLICY",
    "HTTP_RETRY_POLICY",
    "DYNAMODB_RETRY_POLICY",
    "get_retry_policy_for_activity",
    # Infrastructure Models
    "DocumentMetadata",
    # Errors
    "RetryableError",
    "NonRetryableError",
    "WorkflowError",
    "AgentError",
    "StorageError",
    "ConfigurationError",
    "ValidationError",
    # Error classification utilities
    "is_retryable_error",
    "classify_and_wrap_error",
    "create_retryable_error",
    "create_non_retryable_error",
    # Signal Patterns
    "HILSignalsMixin",
    "create_approval_signal",
    "create_feedback_signal",
    "open_approval_review",
    # Query Patterns
    "QueryMixin",
    # Header propagation (worker-side)
    "HeaderPropagationInterceptor",
    "get_header",
    "get_propagated_headers",
    # Header injection (client-side)
    "HeaderInjectionInterceptor",
    "outbound_headers",
    # Observability - import directly from foundry_temporal.observability when needed
    # (not re-exported here to avoid sandbox issues with prometheus_client)
]
