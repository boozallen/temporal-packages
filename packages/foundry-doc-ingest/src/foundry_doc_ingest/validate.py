# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
from dataclasses import dataclass

from temporalio import activity

DEFAULT_SUPPORTED_EXTENSIONS: list[str] = [".pdf", ".txt", ".docx", ".md", ".json"]


@dataclass
class ValidationResult:
    valid: bool
    file_path: str
    error: str | None = None


@activity.defn
def validate_file(
    file_path: str,
    supported_extensions: list[str] | None = None,
) -> ValidationResult:
    """Validate that a file exists, is non-empty, and has a supported extension."""
    extensions = supported_extensions or DEFAULT_SUPPORTED_EXTENSIONS

    if not os.path.exists(file_path):
        return ValidationResult(valid=False, file_path=file_path, error="File not found")

    if os.path.getsize(file_path) == 0:
        return ValidationResult(valid=False, file_path=file_path, error="File is empty")

    _, ext = os.path.splitext(file_path)
    if ext.lower() not in [e.lower() for e in extensions]:
        return ValidationResult(
            valid=False,
            file_path=file_path,
            error=f"Unsupported extension '{ext}'. Supported: {extensions}",
        )

    return ValidationResult(valid=True, file_path=file_path)
