# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Integration tests: malformed signals are silent no-ops through a real worker.

Signals are sent through Temporal's time-skipping test server, the default
workflow sandbox, and the default payload converter. Each test sends rejected
input, checks the workflow state is unchanged and no workflow task failed, then
sends a valid signal and checks the workflow completes.
"""

import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
import pytest_asyncio
from signal_rejection_workflows import FactorySignalWorkflow, MixinSignalWorkflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]

DEPLOY_DIGEST = hashlib.sha256(b"deployment content").hexdigest()
PLAN_DIGEST = hashlib.sha256(b"plan content").hexdigest()
QUERY_TIMEOUT = timedelta(seconds=10)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def env() -> AsyncIterator[WorkflowEnvironment]:
    async with await WorkflowEnvironment.start_time_skipping() as test_env:
        yield test_env


async def _start(env: WorkflowEnvironment, task_queue: str, workflow_run: Any, digest: str) -> WorkflowHandle:
    return await env.client.start_workflow(
        workflow_run,
        digest,
        id=f"signal-rejection-{uuid.uuid4()}",
        task_queue=task_queue,
    )


async def _workflow_task_failed(handle: WorkflowHandle) -> bool:
    async for event in handle.fetch_history_events():
        if event.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED:
            return True
    return False


FACTORY_INITIAL_STATE = {
    "deploy_approved": False,
    "deploy_approved_by": None,
    "deploy_feedback_received": False,
    "deploy_feedback_comments": "",
}

MIXIN_INITIAL_STATE = {
    "plan_approved": False,
    "plan_approved_by": None,
    "plan_feedback_received": False,
    "plan_feedback_comments": "",
    "cancelled": False,
}


@pytest.mark.parametrize(
    ("signal_name", "args"),
    [
        pytest.param("deploy", [], id="approval-no-args"),
        pytest.param("deploy", ["reviewer-1"], id="approval-one-arg"),
        pytest.param("deploy", ["reviewer-1", DEPLOY_DIGEST, "extra"], id="approval-three-args"),
        pytest.param("deploy", ["reviewer-1", "\ud800"], id="approval-lone-surrogate-digest"),
        pytest.param("deploy", ["reviewer-1", "café"], id="approval-non-ascii-digest"),
        pytest.param("deploy", ["reviewer-1", 12345], id="approval-non-string-digest"),
        pytest.param("deploy", [None, DEPLOY_DIGEST], id="approval-null-approver"),
        pytest.param("provide_deploy_feedback", ["please revise"], id="feedback-legacy-comments-only"),
        pytest.param("provide_deploy_feedback", [], id="feedback-no-args"),
        pytest.param("provide_deploy_feedback", [42, "please revise"], id="feedback-non-string-approver"),
    ],
)
async def test_factory_signal_rejected_then_valid_approval_succeeds(
    env: WorkflowEnvironment, signal_name: str, args: list[Any]
) -> None:
    """Rejected factory-signal input leaves state unchanged; a later valid approval completes."""
    # A unique task queue per test keeps one test's worker from running another's workflow.
    task_queue = f"signal-rejection-{uuid.uuid4()}"
    async with Worker(env.client, task_queue=task_queue, workflows=[FactorySignalWorkflow]):
        handle = await _start(env, task_queue, FactorySignalWorkflow.run, DEPLOY_DIGEST)

        await handle.signal(signal_name, args=args)

        assert await handle.query(FactorySignalWorkflow.state, rpc_timeout=QUERY_TIMEOUT) == FACTORY_INITIAL_STATE
        assert not await _workflow_task_failed(handle)

        await handle.signal("deploy", args=["reviewer-1", DEPLOY_DIGEST])
        result = await handle.result(rpc_timeout=timedelta(seconds=30))

        assert result == "reviewer-1"
        assert not await _workflow_task_failed(handle)


@pytest.mark.parametrize(
    ("signal_name", "args"),
    [
        pytest.param("approve_plan", [], id="approve-plan-no-args"),
        pytest.param("approve_plan", ["reviewer-1"], id="approve-plan-one-arg"),
        pytest.param("approve_plan", ["reviewer-1", "\ud800"], id="approve-plan-lone-surrogate-digest"),
        pytest.param("provide_plan_feedback", ["please revise"], id="plan-feedback-legacy-comments-only"),
        pytest.param("cancel_workflow", [], id="cancel-no-args"),
        pytest.param("cancel_workflow", [None], id="cancel-null-approver"),
    ],
)
async def test_mixin_signal_rejected_then_valid_approval_succeeds(
    env: WorkflowEnvironment, signal_name: str, args: list[Any]
) -> None:
    """Rejected mixin-signal input leaves state unchanged; a later valid approval completes."""
    # A unique task queue per test keeps one test's worker from running another's workflow.
    task_queue = f"signal-rejection-{uuid.uuid4()}"
    async with Worker(env.client, task_queue=task_queue, workflows=[MixinSignalWorkflow]):
        handle = await _start(env, task_queue, MixinSignalWorkflow.run, PLAN_DIGEST)

        await handle.signal(signal_name, args=args)

        assert await handle.query(MixinSignalWorkflow.state, rpc_timeout=QUERY_TIMEOUT) == MIXIN_INITIAL_STATE
        assert not await _workflow_task_failed(handle)

        await handle.signal("approve_plan", args=["reviewer-1", PLAN_DIGEST])
        result = await handle.result(rpc_timeout=timedelta(seconds=30))

        assert result == "reviewer-1"
        assert not await _workflow_task_failed(handle)
