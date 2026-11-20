# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from foundry_doc_ingest_aws.s3 import upload_to_s3


def test_successful_upload(sample_file, mock_s3_client):
    key = upload_to_s3(sample_file, bucket="my-bucket", s3_client=mock_s3_client)
    assert key.startswith("document_")
    assert key.endswith(".pdf")
    mock_s3_client.put_object.assert_called_once()
    call_kwargs = mock_s3_client.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "my-bucket"
    assert call_kwargs["Key"] == key


def test_custom_prefix(sample_file, mock_s3_client):
    key = upload_to_s3(sample_file, bucket="my-bucket", key_prefix="documents/", s3_client=mock_s3_client)
    assert key.startswith("documents/document_")


def test_missing_file(mock_s3_client):
    with pytest.raises(FileNotFoundError, match="Source file not found"):
        upload_to_s3("/nonexistent/file.pdf", bucket="my-bucket", s3_client=mock_s3_client)


def test_s3_failure(sample_file):
    client = MagicMock()
    client.put_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        "PutObject",
    )
    with pytest.raises(ClientError):
        upload_to_s3(sample_file, bucket="my-bucket", s3_client=client)


def test_custom_client_injection(sample_file, mock_s3_client):
    upload_to_s3(sample_file, bucket="test-bucket", s3_client=mock_s3_client)
    mock_s3_client.put_object.assert_called_once()
