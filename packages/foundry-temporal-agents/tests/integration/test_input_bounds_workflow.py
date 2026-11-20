# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for InputBoundsError raised from workflow code.

A plain exception in workflow code fails the workflow task, which Temporal
retries indefinitely. Listing InputBoundsError in the worker's
workflow_failure_exception_types fails the workflow instead.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from foundry_temporal_agents import InputBoundsError, _limits
from input_bounds_workflows import OversizedInputWorkflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowFailureError, WorkflowHandle
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

pytestmark = [pytest.mark.integration, pytest.mark.temporal, pytest.mark.asyncio(loop_scope="module")]

OVERSIZED = _limits.MAX_TEXT_LEN + 1
RESULT_TIMEOUT_SECONDS = 30

# Coverage lazily imports its own modules while tracing workflow code; inside
# the sandbox that re-import calls platform.python_implementation(), which the
# sandbox rejects, so the workflow task fails and retries forever.
RUNNER = SandboxedWorkflowRunner(restrictions=SandboxRestrictions.default.with_passthrough_modules("coverage"))


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def env() -> AsyncIterator[WorkflowEnvironment]:
    async with await WorkflowEnvironment.start_time_skipping() as test_env:
        yield test_env


async def _start(env: WorkflowEnvironment, task_queue: str, task_length: int) -> WorkflowHandle:
    return await env.client.start_workflow(
        OversizedInputWorkflow.run,
        task_length,
        id=f"input-bounds-{uuid.uuid4()}",
        task_queue=task_queue,
    )


async def _workflow_task_failure_message(handle: WorkflowHandle) -> str | None:
    async for event in handle.fetch_history_events():
        if event.event_type == EventType.EVENT_TYPE_WORKFLOW_TASK_FAILED:
            return event.workflow_task_failed_event_attributes.failure.message
    return None


async def test_input_within_bounds_completes(env: WorkflowEnvironment):
    """Test that a workflow building an in-bounds input completes."""
    task_queue = f"input-bounds-{uuid.uuid4()}"
    async with Worker(env.client, task_queue=task_queue, workflows=[OversizedInputWorkflow], workflow_runner=RUNNER):
        handle = await _start(env, task_queue, _limits.MAX_TEXT_LEN)
        assert await asyncio.wait_for(handle.result(), RESULT_TIMEOUT_SECONDS) == "xxxxx"


async def test_oversized_input_fails_workflow_when_listed(env: WorkflowEnvironment):
    """Test that listing InputBoundsError in workflow_failure_exception_types fails the workflow."""
    task_queue = f"input-bounds-{uuid.uuid4()}"
    async with Worker(
        env.client,
        task_queue=task_queue,
        workflows=[OversizedInputWorkflow],
        workflow_failure_exception_types=[InputBoundsError],
        workflow_runner=RUNNER,
    ):
        handle = await _start(env, task_queue, OVERSIZED)
        with pytest.raises(WorkflowFailureError) as exc_info:
            await asyncio.wait_for(handle.result(), RESULT_TIMEOUT_SECONDS)

    cause = exc_info.value.cause
    assert isinstance(cause, ApplicationError)
    assert cause.type == "InputBoundsError"
    assert "task exceeds maximum length" in str(cause)


async def test_oversized_input_fails_workflow_task_by_default(env: WorkflowEnvironment):
    """Test that without the setting, the bound violation fails the workflow task instead of the workflow."""
    task_queue = f"input-bounds-{uuid.uuid4()}"
    async with Worker(env.client, task_queue=task_queue, workflows=[OversizedInputWorkflow], workflow_runner=RUNNER):
        handle = await _start(env, task_queue, OVERSIZED)
        message = None
        for _ in range(50):
            message = await _workflow_task_failure_message(handle)
            if message is not None:
                break
            await asyncio.sleep(0.1)
        await handle.terminate("test cleanup")
    assert message is not None
    assert "task exceeds maximum length" in message
