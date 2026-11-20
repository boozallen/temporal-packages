# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Test workflows for test_signal_rejection.py.

Kept in their own top-level module (tests/integration is put on sys.path by
conftest.py) so the Temporal workflow sandbox can re-import them by name.
"""

from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from foundry_temporal.signals import (
        HILSignalsMixin,
        create_approval_signal,
        create_feedback_signal,
        open_approval_review,
    )


@workflow.defn(sandboxed=True)
class FactorySignalWorkflow:
    """Waits on a create_approval_signal-generated "deploy" signal."""

    deploy = create_approval_signal("deploy")
    provide_deploy_feedback = create_feedback_signal("provide_deploy_feedback")

    def __init__(self) -> None:
        self.deploy_approved: bool = False
        self.deploy_approved_by: str | None = None
        self.deploy_feedback_received: bool = False
        self.deploy_feedback_comments: str = ""

    @workflow.run
    async def run(self, digest: str) -> str:
        open_approval_review(self, "deploy", digest)
        await workflow.wait_condition(lambda: self.deploy_approved)
        return self.deploy_approved_by or ""

    @workflow.query
    def state(self) -> dict[str, Any]:
        return {
            "deploy_approved": self.deploy_approved,
            "deploy_approved_by": self.deploy_approved_by,
            "deploy_feedback_received": self.deploy_feedback_received,
            "deploy_feedback_comments": self.deploy_feedback_comments,
        }


@workflow.defn(sandboxed=True)
class MixinSignalWorkflow(HILSignalsMixin):
    """Waits on HILSignalsMixin's approve_plan signal."""

    def __init__(self) -> None:
        super().__init__()

    @workflow.run
    async def run(self, digest: str) -> str:
        self.open_plan_review(digest)
        await workflow.wait_condition(lambda: self.plan_approved or self.cancelled)
        return self.plan_approved_by or ""

    @workflow.query
    def state(self) -> dict[str, Any]:
        return {
            "plan_approved": self.plan_approved,
            "plan_approved_by": self.plan_approved_by,
            "plan_feedback_received": self.plan_feedback_received,
            "plan_feedback_comments": self.plan_feedback_comments,
            "cancelled": self.cancelled,
        }
