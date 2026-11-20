# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from foundry_doc_ingest_aws.bedrock import trigger_kb_sync, wait_for_indexing


def test_successful_trigger(activity_environment, mock_bedrock_client):
    mock_bedrock_client.start_ingestion_job.return_value = {"ingestionJob": {"ingestionJobId": "job-123"}}
    job_id = activity_environment.run(trigger_kb_sync, "kb-1", "ds-1", bedrock_client=mock_bedrock_client)
    assert job_id == "job-123"
    mock_bedrock_client.start_ingestion_job.assert_called_once_with(knowledgeBaseId="kb-1", dataSourceId="ds-1")


def test_invalid_knowledge_base(activity_environment, mock_bedrock_client):
    mock_bedrock_client.start_ingestion_job.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "KB not found"}},
        "StartIngestionJob",
    )
    with pytest.raises(ClientError):
        activity_environment.run(trigger_kb_sync, "invalid-kb", "ds-1", bedrock_client=mock_bedrock_client)


def test_wait_completes_successfully(activity_environment, mock_bedrock_client):
    mock_bedrock_client.get_ingestion_job.return_value = {"ingestionJob": {"status": "COMPLETE"}}
    activity_environment.run(
        wait_for_indexing,
        "kb-1",
        "ds-1",
        "job-123",
        poll_interval=0.01,
        timeout=1.0,
        bedrock_client=mock_bedrock_client,
    )
    mock_bedrock_client.get_ingestion_job.assert_called_once_with(
        knowledgeBaseId="kb-1",
        dataSourceId="ds-1",
        ingestionJobId="job-123",
    )


def test_wait_sync_fails(activity_environment, mock_bedrock_client):
    mock_bedrock_client.get_ingestion_job.return_value = {
        "ingestionJob": {"status": "FAILED", "failureReasons": ["Document parse error"]}
    }
    with pytest.raises(RuntimeError, match="KB sync failed"):
        activity_environment.run(
            wait_for_indexing,
            "kb-1",
            "ds-1",
            "job-123",
            poll_interval=0.01,
            timeout=1.0,
            bedrock_client=mock_bedrock_client,
        )


def test_wait_timeout(activity_environment, mock_bedrock_client):
    mock_bedrock_client.get_ingestion_job.return_value = {"ingestionJob": {"status": "IN_PROGRESS"}}
    # Simulate time advancing past the deadline
    clock = iter([0.0, 0.0, 0.01, 0.02, 0.05])
    with patch("foundry_doc_ingest_aws.bedrock.time.monotonic", side_effect=clock):
        with patch("foundry_doc_ingest_aws.bedrock.time.sleep"):
            with pytest.raises(TimeoutError, match="did not complete"):
                activity_environment.run(
                    wait_for_indexing,
                    "kb-1",
                    "ds-1",
                    "job-123",
                    poll_interval=0.01,
                    timeout=0.03,
                    bedrock_client=mock_bedrock_client,
                )


def test_heartbeat_called(activity_environment, mock_bedrock_client):
    # First call IN_PROGRESS, second call COMPLETE
    mock_bedrock_client.get_ingestion_job.side_effect = [
        {"ingestionJob": {"status": "IN_PROGRESS"}},
        {"ingestionJob": {"status": "COMPLETE"}},
    ]
    heartbeat_count = []
    activity_environment.on_heartbeat = lambda *args: heartbeat_count.append(1)
    with patch("foundry_doc_ingest_aws.bedrock.time.sleep"):
        activity_environment.run(
            wait_for_indexing,
            "kb-1",
            "ds-1",
            "job-123",
            poll_interval=0.01,
            timeout=5.0,
            bedrock_client=mock_bedrock_client,
        )
    assert len(heartbeat_count) == 2


def test_custom_poll_interval(activity_environment, mock_bedrock_client):
    mock_bedrock_client.get_ingestion_job.side_effect = [
        {"ingestionJob": {"status": "IN_PROGRESS"}},
        {"ingestionJob": {"status": "COMPLETE"}},
    ]
    with patch("foundry_doc_ingest_aws.bedrock.time.sleep") as mock_sleep:
        activity_environment.run(
            wait_for_indexing,
            "kb-1",
            "ds-1",
            "job-123",
            poll_interval=5.0,
            timeout=30.0,
            bedrock_client=mock_bedrock_client,
        )
    mock_sleep.assert_called_with(5.0)
