# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Shared input bounds for foundry_temporal signal and header inputs.

STIG V-222612 (SRG-APP-000450): externally-influenced inputs must be bounded to
prevent overflow-style abuse. Signal comment payloads are truncated (Temporal
signal handlers must not raise); injected workflow headers are rejected when the
count or a value exceeds its limit (client-side, fail fast).
"""

import os

MAX_SIGNAL_COMMENT_LENGTH = int(os.getenv("FOUNDRY_TEMPORAL_MAX_COMMENTS_LEN", "8192"))
MAX_HEADER_VALUE_LENGTH = int(os.getenv("FOUNDRY_TEMPORAL_MAX_HEADER_VALUE_LEN", "4096"))
MAX_HEADER_COUNT = int(os.getenv("FOUNDRY_TEMPORAL_MAX_HEADER_COUNT", "50"))


def bound_signal_comment(comments: str | None) -> str:
    """Return ``comments`` truncated to ``MAX_SIGNAL_COMMENT_LENGTH``.

    Signal handlers must never raise (a raised signal handler wedges the workflow
    in a task-retry loop), so oversized comments are clamped rather than rejected,
    and a ``None`` or non-string value is coerced to a string.
    """
    if not isinstance(comments, str):
        comments = "" if comments is None else str(comments)
    if len(comments) > MAX_SIGNAL_COMMENT_LENGTH:
        return comments[:MAX_SIGNAL_COMMENT_LENGTH]
    return comments


def enforce_header_bounds(headers: dict[str, str]) -> None:
    """Raise ``ValueError`` if the header set is too large.

    Enforced at client-side injection so oversized header payloads never enter
    the workflow start / event history.
    """
    if len(headers) > MAX_HEADER_COUNT:
        raise ValueError(f"header count exceeds maximum of {MAX_HEADER_COUNT} (got {len(headers)})")
    for key, value in headers.items():
        if len(value) > MAX_HEADER_VALUE_LENGTH:
            raise ValueError(
                f"header '{key}' value exceeds maximum length of {MAX_HEADER_VALUE_LENGTH} characters "
                f"(got {len(value)})"
            )
