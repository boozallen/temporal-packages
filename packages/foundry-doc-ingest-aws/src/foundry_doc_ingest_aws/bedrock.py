# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import time

import boto3
from botocore.client import BaseClient
from temporalio import activity


@activity.defn
def trigger_kb_sync(
    knowledge_base_id: str,
    data_source_id: str,
    bedrock_client: BaseClient | None = None,
) -> str:
    """Initiate a Bedrock Knowledge Base ingestion job.

    Returns the ingestion job ID.
    """
    client = bedrock_client or boto3.client("bedrock-agent")

    response = client.start_ingestion_job(
        knowledgeBaseId=knowledge_base_id,
        dataSourceId=data_source_id,
    )

    return response["ingestionJob"]["ingestionJobId"]


@activity.defn
def wait_for_indexing(
    knowledge_base_id: str,
    data_source_id: str,
    ingestion_job_id: str,
    poll_interval: float = 10.0,
    timeout: float = 300.0,
    bedrock_client: BaseClient | None = None,
) -> None:
    """Poll until a Bedrock KB ingestion job completes.

    ``data_source_id`` must match the data source used with ``trigger_kb_sync``
    for this ingestion job (required by ``GetIngestionJob``).

    Sends Temporal heartbeats on each poll iteration. Raises TimeoutError
    if the job does not complete within the timeout.
    """
    client = bedrock_client or boto3.client("bedrock-agent")
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        activity.heartbeat()

        response = client.get_ingestion_job(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=data_source_id,
            ingestionJobId=ingestion_job_id,
        )
        status = response["ingestionJob"]["status"]

        if status == "COMPLETE":
            return
        if status == "FAILED":
            reason = response["ingestionJob"].get("failureReasons", ["Unknown error"])
            raise RuntimeError(f"KB sync failed: {reason}")

        time.sleep(poll_interval)

    raise TimeoutError(f"KB sync did not complete within {timeout}s (job: {ingestion_job_id})")
