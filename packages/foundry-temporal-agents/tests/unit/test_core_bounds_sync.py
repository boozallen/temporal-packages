# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Check that the bounds mirrored in _limits.py still match foundry-agent-core.

_limits.py copies the canonical values instead of importing foundry_agent_core,
because the core package root loads cryptography, which crashes Temporal's workflow
sandbox. This test imports core outside the sandbox and fails if a value drifts.
"""

import ast
from pathlib import Path

import foundry_agent_core
import pytest
from foundry_agent_core import types as core_types
from foundry_temporal_agents import _limits


@pytest.mark.parametrize(
    ("mirrored", "canonical"),
    [
        ("CORE_MAX_QUERY_LEN", foundry_agent_core._MAX_QUERY_LEN),
        ("CORE_MAX_DICT_KEYS", foundry_agent_core._MAX_DICT_KEYS),
        ("CORE_MAX_DICT_KEY_LEN", foundry_agent_core._MAX_DICT_KEY_LEN),
        ("CORE_MAX_DICT_BYTES", foundry_agent_core._MAX_DICT_BYTES),
        ("CORE_MAX_RESULTS", foundry_agent_core._MAX_RESULTS),
        ("CORE_MAX_SESSION_ID_LEN", core_types._MAX_SESSION_ID_LEN),
    ],
)
def test_mirrored_bound_matches_core(mirrored, canonical):
    """Test that each mirrored bound equals the value in the installed foundry-agent-core."""
    assert getattr(_limits, mirrored) == canonical


def test_limits_module_does_not_import_core():
    """Test that _limits.py never imports foundry_agent_core, which would break the workflow sandbox."""
    tree = ast.parse(Path(_limits.__file__).read_text())
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(name == "foundry_agent_core" or name.startswith("foundry_agent_core.") for name in imported)
