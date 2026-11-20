# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import uuid

import boto3


def upload_to_s3(
    file_path: str,
    bucket: str,
    key_prefix: str = "",
    s3_client=None,
) -> str:
    """Upload a file to S3 and return the object key.

    This is a plain function — NOT a Temporal activity. Designed to be called
    from the API layer before a workflow starts.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file not found: {file_path}")

    client = s3_client or boto3.client("s3")

    basename = os.path.basename(file_path)
    name, ext = os.path.splitext(basename)
    s3_key = f"{key_prefix}{name}_{uuid.uuid4().hex[:8]}{ext}"

    with open(file_path, "rb") as f:
        client.put_object(Bucket=bucket, Key=s3_key, Body=f)

    return s3_key
