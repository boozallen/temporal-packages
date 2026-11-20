# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for Strands agent dataclass models and their STIG V-222612 dict bounds"""

import dataclasses
import importlib

import pytest
from foundry_temporal_agents import InputBoundsError, _limits
from foundry_temporal_agents.models import StrandsAgentTaskInput
from temporalio.converter import default as default_converter

DICT_FIELDS = ["query_extra_data", "additional_params"]


@dataclasses.dataclass
class _HiddenBlob:
    blob: str = dataclasses.field(repr=False)


class TestStrandsAgentTaskInput:
    """Test suite for StrandsAgentTaskInput dataclass."""

    def test_minimal_valid_input(self):
        """Test that only task is required and dict fields default to empty."""
        input_data = StrandsAgentTaskInput(task="summarize the document")

        assert input_data.task == "summarize the document"
        assert input_data.query_extra_data == {}
        assert input_data.session_id is None
        assert input_data.additional_params == {}

    def test_normal_payload_accepted(self):
        """Test that a typical payload passes the default bounds."""
        input_data = StrandsAgentTaskInput(
            task="analyze",
            query_extra_data={"user_id": "12345", "source": "web"},
            session_id="session-abc123",
            additional_params={"priority": "high"},
        )

        assert input_data.query_extra_data == {"user_id": "12345", "source": "web"}
        assert input_data.additional_params == {"priority": "high"}

    @pytest.mark.parametrize("field_name", DICT_FIELDS)
    def test_dict_at_key_limit_accepted(self, field_name):
        """Test that a dict at the key limit is accepted."""
        at_limit = {f"k{i}": i for i in range(_limits.MAX_DICT_KEYS)}
        input_data = StrandsAgentTaskInput(task="t", **{field_name: at_limit})
        assert getattr(input_data, field_name) == at_limit

    @pytest.mark.parametrize("field_name", DICT_FIELDS)
    def test_dict_over_key_limit_rejected(self, field_name):
        """Test that a dict above the key limit raises ValueError naming the field."""
        oversized = {f"k{i}": i for i in range(_limits.MAX_DICT_KEYS + 1)}
        with pytest.raises(ValueError, match=f"{field_name} exceeds maximum of"):
            StrandsAgentTaskInput(task="t", **{field_name: oversized})

    @pytest.mark.parametrize("field_name", DICT_FIELDS)
    def test_dict_over_byte_limit_rejected(self, field_name):
        """Test that a dict above the serialized size limit raises ValueError naming the field."""
        oversized = {"blob": "x" * _limits.MAX_DICT_BYTES}
        with pytest.raises(ValueError, match=f"{field_name} serializes above"):
            StrandsAgentTaskInput(task="t", **{field_name: oversized})

    @pytest.mark.parametrize(
        "value",
        [
            {"k": "ascii text"},
            {"note": "\u6f22" * 100},
            {"emoji": "\U0001f600" * 10},
            {"k": "\ud800"},
            {"nested": {"a": [1, 2.5, None, True]}},
            {"z": 1, "a": 2},
            {"doc": _HiddenBlob(blob="hidden " * 50)},
        ],
    )
    def test_size_matches_temporal_payload_bytes(self, value):
        """Test that the size contract equals the bytes Temporal's default JSON converter sends."""
        payload = default_converter().payload_converter.to_payloads([value])[0]
        assert _limits.serialized_size(value) == len(payload.data)

    def test_nested_dataclass_measured_by_contents(self):
        """Test that a nested dataclass counts its hidden fields, as Temporal expands it on the wire."""
        oversized = {"doc": _HiddenBlob(blob="x" * _limits.MAX_PAYLOAD_BYTES)}
        with pytest.raises(InputBoundsError, match="additional_params serializes above"):
            StrandsAgentTaskInput(task="t", additional_params=oversized)

    def test_unencodable_value_rejected(self):
        """Test that a value Temporal's JSON converter cannot encode raises InputBoundsError."""
        with pytest.raises(InputBoundsError, match="cannot be encoded"):
            StrandsAgentTaskInput(task="t", additional_params={"obj": object()})

    def test_dict_byte_limit_counts_escaped_bytes(self):
        """Test that non-ASCII text counts at its escaped size, as Temporal sends it."""
        # Each CJK character escapes to 6 bytes (\uXXXX).
        fits = (_limits.MAX_DICT_BYTES - 20) // 6
        StrandsAgentTaskInput(task="t", query_extra_data={"note": "\u6f22" * fits})

        with pytest.raises(ValueError, match="query_extra_data serializes above"):
            StrandsAgentTaskInput(task="t", query_extra_data={"note": "\u6f22" * (_limits.MAX_DICT_BYTES // 6 + 1)})

    def test_payload_check_does_not_deep_copy(self, monkeypatch):
        """Test that the whole-input check measures the fields in place instead of deep-copying them."""
        import copy

        def fail_deepcopy(*args, **kwargs):
            raise AssertionError("StrandsAgentTaskInput deep-copied its fields")

        monkeypatch.setattr(copy, "deepcopy", fail_deepcopy)
        StrandsAgentTaskInput(task="t", query_extra_data={"nested": {"a": [1, 2]}}, additional_params={"p": [3]})

    def test_task_none_rejected(self):
        """Test that task is required to be a string at construction."""
        with pytest.raises(InputBoundsError, match="task must be a string"):
            StrandsAgentTaskInput(task=None)  # type: ignore[arg-type]

    def test_whole_input_over_payload_limit_rejected(self):
        """Test that fields each within their own limit are rejected when the whole input exceeds the payload limit."""
        # Non-ASCII task text: within MAX_TEXT_LEN characters, but six bytes each on the wire.
        task = "\u6f22" * _limits.MAX_TEXT_LEN
        with pytest.raises(InputBoundsError, match="StrandsAgentTaskInput serializes above"):
            StrandsAgentTaskInput(task=task)

    def test_dict_with_lone_surrogate_accepted(self):
        """Test that a lone surrogate, which JSON can carry, is measured instead of crashing the size check."""
        input_data = StrandsAgentTaskInput(task="t", query_extra_data={"k": "\ud800"})
        assert input_data.query_extra_data == {"k": "\ud800"}

    def test_dict_key_over_length_limit_rejected(self):
        """Test that an over-long dict key raises ValueError."""
        with pytest.raises(ValueError, match="query_extra_data has a key longer than"):
            StrandsAgentTaskInput(task="t", query_extra_data={"k" * (_limits.MAX_DICT_KEY_LEN + 1): 1})

    def test_text_fields_at_limit_accepted(self):
        """Test that task and session_id at their length limits are accepted."""
        input_data = StrandsAgentTaskInput(
            task="x" * _limits.MAX_TEXT_LEN,
            session_id="s" * _limits.MAX_SESSION_ID_LEN,
        )

        assert len(input_data.task) == _limits.MAX_TEXT_LEN
        assert input_data.session_id is not None
        assert len(input_data.session_id) == _limits.MAX_SESSION_ID_LEN

    def test_task_over_length_limit_rejected(self):
        """Test that an over-long task raises ValueError."""
        with pytest.raises(ValueError, match="task exceeds maximum length"):
            StrandsAgentTaskInput(task="x" * (_limits.MAX_TEXT_LEN + 1))

    def test_session_id_over_length_limit_rejected(self):
        """Test that an over-long session_id raises ValueError."""
        with pytest.raises(ValueError, match="session_id exceeds maximum length"):
            StrandsAgentTaskInput(task="t", session_id="s" * (_limits.MAX_SESSION_ID_LEN + 1))

    def test_dict_bounds_enforced_on_worker_reconstruction(self, temporal_style_input):
        """Test that rebuilding the dataclass from its wire dict enforces the bounds."""
        payload = temporal_style_input(StrandsAgentTaskInput(task="t"))
        payload["additional_params"] = {f"k{i}": i for i in range(_limits.MAX_DICT_KEYS + 1)}
        with pytest.raises(ValueError, match="additional_params exceeds maximum of"):
            StrandsAgentTaskInput(**payload)

    def test_is_dataclass(self):
        """Test that the model stays a dataclass."""
        assert dataclasses.is_dataclass(StrandsAgentTaskInput)


class TestDictLimitConfiguration:
    """Test suite for env-configurable dict bounds."""

    @pytest.fixture
    def reload_limits(self, monkeypatch):
        """Reload _limits after env changes, then restore the original env and reload again."""
        yield lambda: importlib.reload(_limits)
        monkeypatch.undo()
        importlib.reload(_limits)

    def test_defaults_when_env_unset(self, monkeypatch, reload_limits):
        """Test the default bounds when no env vars are set."""
        for name in (
            "FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEYS",
            "FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEY_LEN",
            "FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_BYTES",
            "FOUNDRY_TEMPORAL_AGENTS_MAX_TEXT_LEN",
            "FOUNDRY_TEMPORAL_AGENTS_MAX_SESSION_ID_LEN",
            "FOUNDRY_TEMPORAL_AGENTS_MAX_PAYLOAD_BYTES",
        ):
            monkeypatch.delenv(name, raising=False)
        limits = reload_limits()

        assert limits.MAX_DICT_KEYS == 32
        assert limits.MAX_DICT_KEY_LEN == 128
        assert limits.MAX_DICT_BYTES == 524288
        assert limits.MAX_TEXT_LEN == 524288
        assert limits.MAX_PAYLOAD_BYTES == 2031616
        assert limits.MAX_SESSION_ID_LEN == 128

    def test_defaults_derive_from_core_capped_by_temporal(self, monkeypatch, reload_limits):
        """Test that each default is the core bound, capped by the Temporal transport limit where one applies."""
        import foundry_agent_core

        for name in (
            "FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEYS",
            "FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEY_LEN",
            "FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_BYTES",
            "FOUNDRY_TEMPORAL_AGENTS_MAX_TEXT_LEN",
            "FOUNDRY_TEMPORAL_AGENTS_MAX_SESSION_ID_LEN",
        ):
            monkeypatch.delenv(name, raising=False)
        limits = reload_limits()

        assert limits.MAX_DICT_KEYS == foundry_agent_core._MAX_DICT_KEYS
        assert limits.MAX_DICT_KEY_LEN == foundry_agent_core._MAX_DICT_KEY_LEN
        assert limits.MAX_RESULTS_RANGE == (1, foundry_agent_core._MAX_RESULTS)
        assert limits.MAX_DICT_BYTES == min(foundry_agent_core._MAX_DICT_BYTES, limits.TEMPORAL_MAX_FIELD_BYTES)
        assert limits.MAX_TEXT_LEN == min(foundry_agent_core._MAX_QUERY_LEN, limits.TEMPORAL_MAX_FIELD_BYTES)

    def test_env_overrides_session_id_limit(self, monkeypatch, reload_limits):
        """Test that FOUNDRY_TEMPORAL_AGENTS_MAX_SESSION_ID_LEN changes the enforced session_id length."""
        monkeypatch.setenv("FOUNDRY_TEMPORAL_AGENTS_MAX_SESSION_ID_LEN", "6")
        limits = reload_limits()

        assert limits.MAX_SESSION_ID_LEN == 6
        with pytest.raises(ValueError, match="session_id exceeds maximum length of 6 characters"):
            limits.validate_bounded_str("sess-1285", "session_id", limits.MAX_SESSION_ID_LEN)

    def test_env_overrides_text_and_payload_limits(self, monkeypatch, reload_limits):
        """Test that the text and whole-input limits can be changed through their env vars."""
        monkeypatch.setenv("FOUNDRY_TEMPORAL_AGENTS_MAX_TEXT_LEN", "5")
        monkeypatch.setenv("FOUNDRY_TEMPORAL_AGENTS_MAX_PAYLOAD_BYTES", "50")
        limits = reload_limits()

        with pytest.raises(ValueError, match="maximum length of 5 characters"):
            limits.validate_bounded_str("abcdef", "task", limits.MAX_TEXT_LEN)
        with pytest.raises(ValueError, match="maximum of 50 bytes"):
            limits.validate_payload_size({"k": "x" * 50}, "input")

    def test_env_overrides_key_limit(self, monkeypatch, reload_limits):
        """Test that FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEYS changes the enforced key limit."""
        monkeypatch.setenv("FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEYS", "4")
        limits = reload_limits()

        assert limits.validate_bounded_dict({f"k{i}": i for i in range(4)}, "f") is not None
        with pytest.raises(ValueError, match="maximum of 4 keys"):
            limits.validate_bounded_dict({f"k{i}": i for i in range(5)}, "f")

    def test_env_overrides_byte_limit(self, monkeypatch, reload_limits):
        """Test that FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_BYTES changes the enforced size limit."""
        monkeypatch.setenv("FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_BYTES", "20")
        limits = reload_limits()

        with pytest.raises(ValueError, match="maximum of 20 bytes"):
            limits.validate_bounded_dict({"blob": "x" * 20}, "f")

    def test_env_overrides_key_length_limit(self, monkeypatch, reload_limits):
        """Test that FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEY_LEN changes the enforced key length."""
        monkeypatch.setenv("FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_KEY_LEN", "3")
        limits = reload_limits()

        with pytest.raises(ValueError, match="longer than 3 characters"):
            limits.validate_bounded_dict({"abcd": 1}, "f")
