# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Base data models for foundry_temporal

These models support the foundry_temporal infrastructure and are separate from
template-specific models that teams customize in their own models.py files.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentMetadata(BaseModel):
    """
    Document metadata for workflow-managed persistence

    Used by storage.py for tracking document versions and metadata.
    Based on foundry-temporal design specification.
    """

    workflow_id: str = Field(..., description="Workflow ID that created the document")
    version: int = Field(..., description="Document version number")
    doc_type: Literal["draft", "final"] = Field(..., description="Document type")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    document_key: str = Field(..., description="Unique document key")
    approved: bool = Field(default=False, description="Whether document is approved")
    updated_at: str | None = Field(default=None, description="Last update timestamp (ISO format)")
    content_size: int | None = Field(default=None, description="Document content size in bytes")
    iteration_count: int | None = Field(default=None, description="Number of iterations/revisions")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "workflow_id": "research-workflow-123",
                    "version": 1,
                    "doc_type": "draft",
                    "created_at": "2023-12-01T10:30:00Z",
                    "document_key": "research-report-123",
                    "approved": False,
                }
            ]
        }
    )
