# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Foundry Doc Ingest AWS — AWS integration for document ingestion pipelines.

Provides S3 upload (API-layer) and Bedrock Knowledge Base sync (Temporal activities).
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("foundry-doc-ingest-aws")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from .bedrock import trigger_kb_sync, wait_for_indexing
from .s3 import upload_to_s3

__all__ = [
    "upload_to_s3",
    "trigger_kb_sync",
    "wait_for_indexing",
]
