# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Models for Strands Query API requests and responses."""

import json
import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAX_DICT_KEYS = int(os.getenv("FOUNDRY_STRANDS_AGENTS_MAX_DICT_KEYS", "32"))
_MAX_DICT_KEY_LEN = int(os.getenv("FOUNDRY_STRANDS_AGENTS_MAX_DICT_KEY_LEN", "128"))
_MAX_DICT_BYTES = int(os.getenv("FOUNDRY_STRANDS_AGENTS_MAX_DICT_BYTES", "16384"))


def _validate_bounded_dict(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate dict fields against STIG V-222612 overflow bounds."""
    if value is None:
        return None
    if len(value) > _MAX_DICT_KEYS:
        raise ValueError(f"dict exceeds {_MAX_DICT_KEYS} top-level keys")
    for key in value:
        if len(key) > _MAX_DICT_KEY_LEN:
            raise ValueError(f"dict key exceeds {_MAX_DICT_KEY_LEN} characters")
    if len(json.dumps(value, default=str)) > _MAX_DICT_BYTES:
        raise ValueError(f"dict serializes above {_MAX_DICT_BYTES} bytes")
    return value


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
        max_length=10000,
    )

    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional context information to help with query processing",
    )

    session_id: str | None = Field(
        default=None,
        description="Optional session identifier for conversation continuity",
        min_length=3,
        max_length=40,
    )

    max_results: int = Field(
        default=10,
        description="Maximum number of results to return",
        ge=1,
        le=100,
    )

    similarity_threshold: float = Field(
        default=0.7,
        description="Minimum similarity threshold for results (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )

    additional_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional parameters forwarded to the query API",
    )

    @field_validator("context", "additional_params", mode="after")
    @classmethod
    def _validate_dict_bounds(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_bounded_dict(v)

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
