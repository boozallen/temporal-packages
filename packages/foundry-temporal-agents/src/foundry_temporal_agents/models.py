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

from dataclasses import dataclass, field, fields
from typing import Any

from ._limits import (
    MAX_SESSION_ID_LEN,
    MAX_TEXT_LEN,
    validate_bounded_dict,
    validate_bounded_str,
    validate_payload_size,
)


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

    def __post_init__(self) -> None:
        # STIG V-222612: reject oversized inputs before they reach Temporal.
        validate_bounded_str(self.task, "task", MAX_TEXT_LEN, required=True)
        validate_bounded_str(self.session_id, "session_id", MAX_SESSION_ID_LEN)
        validate_bounded_dict(self.query_extra_data, "query_extra_data")
        validate_bounded_dict(self.additional_params, "additional_params")
        # A shallow view serializes the same as asdict() without deep-copying every value.
        validate_payload_size({f.name: getattr(self, f.name) for f in fields(self)}, "StrandsAgentTaskInput")
