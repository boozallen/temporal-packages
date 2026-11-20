# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Models for Strands Query API requests and responses."""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from ._limits import (
    MAX_RESULTS_RANGE,
    MAX_SESSION_ID_LEN,
    MAX_TEXT_LEN,
    SIMILARITY_THRESHOLD_RANGE,
    validate_bounded_dict,
    validate_payload_size,
)


class StrandsQueryTaskInput(BaseModel):
    """
    Input dataclass for query-based Strands agent tasks.

    This dataclass follows Temporal best practices by providing a single
    structured input parameter that can evolve over time. It contains all
    the parameters needed for a query API call to a Strands agent.
    """

    query: str = Field(
        ...,
        description="The user's question or query to be processed by the agent",
        min_length=1,
        max_length=MAX_TEXT_LEN,
    )

    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional context information to help with query processing",
    )

    session_id: str | None = Field(
        default=None,
        description="Optional session identifier for conversation continuity",
        min_length=3,
        max_length=MAX_SESSION_ID_LEN,
    )

    max_results: int = Field(
        default=10,
        description="Maximum number of results to return",
        ge=MAX_RESULTS_RANGE[0],
        le=MAX_RESULTS_RANGE[1],
    )

    similarity_threshold: float = Field(
        default=0.7,
        description="Minimum similarity threshold for results (0.0 to 1.0)",
        ge=SIMILARITY_THRESHOLD_RANGE[0],
        le=SIMILARITY_THRESHOLD_RANGE[1],
    )

    additional_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional parameters forwarded to the query API",
    )

    @field_validator("context", "additional_params", mode="after")
    @classmethod
    def _validate_dict_bounds(cls, v: dict[str, Any] | None, info: ValidationInfo) -> dict[str, Any] | None:
        # STIG V-222612: reject oversized dict inputs before they reach Temporal.
        return validate_bounded_dict(v, info.field_name or "dict")

    @model_validator(mode="after")
    def _validate_payload_size(self) -> Self:
        # STIG V-222612: the whole input must fit in one Temporal payload.
        validate_payload_size(self.model_dump(), "StrandsQueryTaskInput")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "query": "What are the main features of this system?",
                    "context": {"user_id": "12345", "source": "web"},
                    "session_id": "session-abc123",
                    "max_results": 10,
                    "similarity_threshold": 0.8,
                    "additional_params": {"priority": "high"},
                }
            ]
        }
    )
