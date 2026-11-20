# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Query Pattern Helpers

Standard query patterns based on foundry-temporal architecture specifications.
"""

from typing import Any

from temporalio import workflow


class QueryMixin:
    """
    Mixin class providing standard query patterns

    From architecture specification:
    Queries (status polling via API Gateway):
    - get_status() -> dict - Current workflow state
    """

    def __init__(self):
        # Ensure these attributes exist for queries
        if not hasattr(self, "workflow_id"):
            self.workflow_id = "unknown"
        if not hasattr(self, "current_phase"):
            self.current_phase = "initializing"

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        """
        Get current workflow status

        From architecture: Current workflow state (plan/document iteration,
        approval status, awaiting review flags)
        """
        return {
            "workflow_id": getattr(self, "workflow_id", "unknown"),
            "current_phase": getattr(self, "current_phase", "unknown"),
            "iteration": getattr(self, "iteration", 0),
            "approved": getattr(self, "approved", False),
            "approved_by": getattr(self, "approved_by", None),
            "plan_approved_by": getattr(self, "plan_approved_by", None),
            "document_approved_by": getattr(self, "document_approved_by", None),
            "awaiting_feedback": getattr(self, "awaiting_feedback", False),
            "current_document_key": getattr(self, "current_document_key", None),
            "last_updated": workflow.now().isoformat(),
        }
