# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Workflows that build an oversized activity input in workflow code."""

# Imported normally, not passed through the sandbox, so these tests also prove that
# workflow code can import foundry_temporal_agents inside Temporal's sandbox.
from foundry_temporal_agents import StrandsAgentTaskInput
from temporalio import workflow


@workflow.defn
class OversizedInputWorkflow:
    """Builds a StrandsAgentTaskInput whose task exceeds the STIG V-222612 length bound."""

    @workflow.run
    async def run(self, task_length: int) -> str:
        return StrandsAgentTaskInput(task="x" * task_length).task[:5]
