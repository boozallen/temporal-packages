# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Foundry Doc Ingest — Document ingestion activities for Temporal workflows.

Provides three core activity functions for local document pipelines:
- validate_file: Check file existence, size, and extension
- store_file: Copy files to local storage with unique naming
- update_provenance: Track workflow run records in SQLite
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("foundry-doc-ingest")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from .local import store_file
from .provenance import ProvenanceRecord, get_provenance, init_provenance_db, update_provenance
from .validate import ValidationResult, validate_file

__all__ = [
    "validate_file",
    "ValidationResult",
    "store_file",
    "update_provenance",
    "get_provenance",
    "init_provenance_db",
    "ProvenanceRecord",
]
