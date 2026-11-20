# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Dataclass models for Strands agent activity inputs following Temporal best practices.

This module provides recommended patterns for structuring activity inputs as dataclasses,
which enables:
- Better type safety and IDE support
- Easier evolution of activity interfaces
- Standardized activity patterns
- Alignment with Temporal best practices
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrandsAgentTaskInput:
    """
    Recommended dataclass input for Strands agent activities.

    This pattern standardizes activity inputs into a single dataclass parameter,
    making it easier to add/remove fields over time without changing function signatures.

    Example usage:
        @strands_agent_activity(name="process_document")
        async def process_document_activity(input_data: StrandsAgentTaskInput) -> dict:
            return {
                "task": input_data.task,
                "context": {"source": input_data.session_id},
            }
    """

    task: str
    """The task description to send to the agent"""

    query_extra_data: dict[str, Any] = field(default_factory=dict)
    """Optional context payload included in the message body"""

    session_id: str | None = None
    """Optional conversation/session identifier for maintaining context"""

    additional_params: dict[str, Any] = field(default_factory=dict)
    """Additional parameters forwarded to the agent request"""
