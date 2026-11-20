# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Shared input bounds for foundry_temporal_agents activity inputs.

STIG V-222612 (SRG-APP-000450): externally-influenced inputs must be bounded to
prevent overflow-style abuse. The user-supplied dict fields on
``StrandsQueryTaskInput`` and ``StrandsAgentTaskInput`` are rejected when the key
count, a key length, or the serialized size exceeds its limit. The text fields
(query/task and session_id) share length limits across both models and the
dict-returning activity paths.

Defaults mirror the canonical bounds in ``foundry_agent_core``. The text and dict
size defaults are also capped by Temporal transport limits, because these inputs
travel as one Temporal payload and the core defaults (2 MiB of text, 4 MiB per dict)
exceed Temporal's 2 MiB payload limit on their own.

Size contract: a dict or whole input is measured as Temporal's default JSON payload
converter serializes it, compact separators and escaped non-ASCII, so the limits
track the bytes Temporal actually sends. ``foundry_agent_core`` also measures escaped
JSON, but with default separators, so its counts run slightly higher.
"""

import json
import math
import os
from typing import Any

from temporalio.converter import AdvancedJSONEncoder
from temporalio.exceptions import ApplicationError

from .exceptions import InputBoundsError

# Canonical bounds mirrored from foundry_agent_core/types.py. They are copied, not
# imported: foundry_agent_core's package root loads cryptography, which crashes
# Temporal's workflow sandbox when workflow code imports this package.
# tests/unit/test_core_bounds_sync.py fails if these drift from foundry-agent-core.
CORE_MAX_QUERY_LEN = 2_097_152
CORE_MAX_SESSION_ID_LEN = 128
CORE_MAX_DICT_KEYS = 32
CORE_MAX_DICT_KEY_LEN = 128
CORE_MAX_DICT_BYTES = 4_194_304
CORE_MAX_RESULTS = 100

# Temporal transport limits. The server rejects a payload above 2 MiB by default and
# warns above 512 KiB, so each large field is capped at the warning size. The whole
# input model is capped 64 KiB under the rejection size, because the same activity
# call also carries the other arguments, such as agent_url, and payload metadata.
TEMPORAL_MAX_PAYLOAD_BYTES = 2_097_152
TEMPORAL_PAYLOAD_HEADROOM_BYTES = 65_536
TEMPORAL_MAX_FIELD_BYTES = 524_288

MAX_DICT_KEYS = int(os.getenv("FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEYS", str(CORE_MAX_DICT_KEYS)))
MAX_DICT_KEY_LEN = int(os.getenv("FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEY_LEN", str(CORE_MAX_DICT_KEY_LEN)))
MAX_DICT_BYTES = int(
    os.getenv("FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_BYTES", str(min(CORE_MAX_DICT_BYTES, TEMPORAL_MAX_FIELD_BYTES)))
)
MAX_TEXT_LEN = int(
    os.getenv("FOUNDRY_TEMPORAL_AGENTS_MAX_TEXT_LEN", str(min(CORE_MAX_QUERY_LEN, TEMPORAL_MAX_FIELD_BYTES)))
)
MAX_PAYLOAD_BYTES = int(
    os.getenv(
        "FOUNDRY_TEMPORAL_AGENTS_MAX_PAYLOAD_BYTES",
        str(TEMPORAL_MAX_PAYLOAD_BYTES - TEMPORAL_PAYLOAD_HEADROOM_BYTES),
    )
)
MAX_SESSION_ID_LEN = int(os.getenv("FOUNDRY_TEMPORAL_AGENTS_MAX_SESSION_ID_LEN", str(CORE_MAX_SESSION_ID_LEN)))
MAX_RESULTS_RANGE = (1, CORE_MAX_RESULTS)
SIMILARITY_THRESHOLD_RANGE = (0.0, 1.0)


def serialized_size(value: object) -> int:
    """Return the size of ``value`` as Temporal's default JSON payload converter encodes it.

    Uses the converter's own encoder and settings, so nested dataclasses are measured
    field by field, as sent. A value the converter cannot encode raises ``InputBoundsError``.
    """
    try:
        return len(json.dumps(value, cls=AdvancedJSONEncoder, separators=(",", ":"), sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise InputBoundsError(f"value cannot be encoded by Temporal's JSON payload converter: {exc}") from exc


def validate_bounded_dict(value: dict[str, Any] | None, field_name: str) -> dict[str, Any] | None:
    """Return ``value`` unchanged, or raise ``InputBoundsError`` if it exceeds a dict bound."""
    if value is None:
        return None
    if len(value) > MAX_DICT_KEYS:
        raise InputBoundsError(f"{field_name} exceeds maximum of {MAX_DICT_KEYS} keys (got {len(value)})")
    for key in value:
        if len(str(key)) > MAX_DICT_KEY_LEN:
            raise InputBoundsError(f"{field_name} has a key longer than {MAX_DICT_KEY_LEN} characters")
    size = serialized_size(value)
    if size > MAX_DICT_BYTES:
        raise InputBoundsError(f"{field_name} serializes above maximum of {MAX_DICT_BYTES} bytes (got {size})")
    return value


def validate_payload_size(value: object, name: str) -> None:
    """Raise ``InputBoundsError`` if ``value`` would serialize above ``MAX_PAYLOAD_BYTES``.

    Per-field limits cannot bound non-ASCII text on their own, because each such
    character escapes to six or twelve bytes on the wire.
    """
    size = serialized_size(value)
    if size > MAX_PAYLOAD_BYTES:
        raise InputBoundsError(f"{name} serializes above maximum of {MAX_PAYLOAD_BYTES} bytes (got {size})")


def validate_bounded_str(value: object, field_name: str, max_len: int, required: bool = False) -> str | None:
    """Return ``value`` unchanged, or raise ``InputBoundsError`` if it is not a string or is longer than ``max_len``.

    ``None`` passes only when ``required`` is false. Checking the type first means
    a large non-string value is rejected without first being converted to an
    equally large string.
    """
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise InputBoundsError(f"{field_name} must be a string (got {type(value).__name__})")
    if len(value) > max_len:
        raise InputBoundsError(f"{field_name} exceeds maximum length of {max_len} characters (got {len(value)})")
    return value


def validate_number_range(value: float, field_name: str, bounds: tuple[float, float]) -> float:
    """Return ``value`` unchanged, or raise ``InputBoundsError`` if it is not finite or outside ``bounds``.

    Integer ``bounds`` also require a whole-number ``value``. The range is compared
    before any float conversion, so an arbitrarily large int cannot overflow.
    """
    low, high = bounds
    if isinstance(value, float) and not math.isfinite(value):
        raise InputBoundsError(f"{field_name} must be a finite number (got {value})")
    if not low <= value <= high:
        raise InputBoundsError(f"{field_name} must be between {low} and {high} (got {value})")
    if isinstance(low, int) and isinstance(high, int) and isinstance(value, float) and not value.is_integer():
        raise InputBoundsError(f"{field_name} must be a whole number (got {value})")
    return value


def enforce_activity_input_bounds(
    text: object,
    text_field: str,
    session_id: object,
    dicts: dict[str, dict[str, Any]],
    ranges: dict[str, tuple[float, tuple[float, float]]] | None = None,
) -> None:
    """Raise a non-retryable ``ApplicationError`` if an activity's built input exceeds a bound.

    Used by the dict-returning activity paths, which assemble the agent request
    without going through ``StrandsQueryTaskInput`` or ``StrandsAgentTaskInput``.
    Non-retryable because the same input fails the same way on every attempt.
    """
    try:
        validate_bounded_str(text, text_field, MAX_TEXT_LEN, required=True)
        if isinstance(session_id, str):
            validate_bounded_str(session_id, "session_id", MAX_SESSION_ID_LEN)
        for field_name, value in dicts.items():
            validate_bounded_dict(value, field_name)
        for field_name, (number, bounds) in (ranges or {}).items():
            validate_number_range(number, field_name, bounds)
    except ValueError as e:
        raise ApplicationError(str(e), non_retryable=True, type="InvalidActivityInput") from e
