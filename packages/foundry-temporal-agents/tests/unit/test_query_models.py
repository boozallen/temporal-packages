# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for Strands Query API models"""

import pytest
from foundry_temporal_agents import _limits
from foundry_temporal_agents.query_models import StrandsQueryTaskInput
from pydantic import ValidationError


class TestStrandsQueryTaskInput:
    """Test suite for StrandsQueryTaskInput model."""

    def test_minimal_valid_input(self):
        """Test creating input with minimal valid data."""
        input_data = StrandsQueryTaskInput(query="What are the main features?")

        assert input_data.query == "What are the main features?"
        assert input_data.context is None
        assert input_data.session_id is None
        assert input_data.max_results == 10
        assert input_data.similarity_threshold == 0.7
        assert input_data.additional_params == {}

    def test_full_valid_input(self):
        """Test creating input with all fields populated."""
        input_data = StrandsQueryTaskInput(
            query="Explain the architecture",
            context={"user_id": "123", "source": "web"},
            session_id="session-abc123",
            max_results=25,
            similarity_threshold=0.9,
            additional_params={"priority": "high", "timeout": 300},
        )

        assert input_data.query == "Explain the architecture"
        assert input_data.context == {"user_id": "123", "source": "web"}
        assert input_data.session_id == "session-abc123"
        assert input_data.max_results == 25
        assert input_data.similarity_threshold == 0.9
        assert input_data.additional_params == {"priority": "high", "timeout": 300}

    def test_empty_query_validation(self):
        """Test that empty query raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query="")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "string_too_short"
        assert errors[0]["loc"] == ("query",)

    def test_long_query_validation(self):
        """Test that overly long query raises validation error."""
        long_query = "x" * (_limits.MAX_TEXT_LEN + 1)

        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query=long_query)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "string_too_long"
        assert errors[0]["loc"] == ("query",)

    def test_short_session_id_validation(self):
        """Test that short session_id raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query="test", session_id="ab")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "string_too_short"
        assert errors[0]["loc"] == ("session_id",)

    def test_long_session_id_validation(self):
        """Test that overly long session_id raises validation error."""
        long_session_id = "x" * (_limits.MAX_SESSION_ID_LEN + 1)

        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query="test", session_id=long_session_id)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "string_too_long"
        assert errors[0]["loc"] == ("session_id",)

    def test_max_results_validation_too_low(self):
        """Test that max_results below 1 raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query="test", max_results=0)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "greater_than_equal"
        assert errors[0]["loc"] == ("max_results",)

    def test_max_results_validation_too_high(self):
        """Test that max_results above 100 raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query="test", max_results=101)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "less_than_equal"
        assert errors[0]["loc"] == ("max_results",)

    def test_similarity_threshold_validation_too_low(self):
        """Test that similarity_threshold below 0.0 raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query="test", similarity_threshold=-0.1)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "greater_than_equal"
        assert errors[0]["loc"] == ("similarity_threshold",)

    def test_similarity_threshold_validation_too_high(self):
        """Test that similarity_threshold above 1.0 raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query="test", similarity_threshold=1.1)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "less_than_equal"
        assert errors[0]["loc"] == ("similarity_threshold",)

    def test_boundary_values(self):
        """Test boundary values for numeric fields."""
        input_data = StrandsQueryTaskInput(query="test", max_results=1, similarity_threshold=0.0)
        assert input_data.max_results == 1
        assert input_data.similarity_threshold == 0.0

        input_data = StrandsQueryTaskInput(query="test", max_results=100, similarity_threshold=1.0)
        assert input_data.max_results == 100
        assert input_data.similarity_threshold == 1.0

    def test_none_values_for_optional_fields(self):
        """Test that None values work for optional fields."""
        input_data = StrandsQueryTaskInput(query="test", context=None, session_id=None)

        assert input_data.context is None
        assert input_data.session_id is None

    def test_empty_additional_params(self):
        """Test that additional_params defaults to empty dict."""
        input_data = StrandsQueryTaskInput(query="test")
        assert input_data.additional_params == {}

    def test_custom_additional_params(self):
        """Test custom additional_params."""
        custom_params = {"priority": "high", "timeout": 300, "retries": 3}
        input_data = StrandsQueryTaskInput(query="test", additional_params=custom_params)
        assert input_data.additional_params == custom_params

    @pytest.mark.parametrize("field_name", ["context", "additional_params"])
    def test_dict_at_key_limit_accepted(self, field_name):
        """Test that a dict at the key limit is accepted (STIG V-222612)."""
        at_limit = {f"k{i}": i for i in range(_limits.MAX_DICT_KEYS)}
        input_data = StrandsQueryTaskInput(query="test", **{field_name: at_limit})
        assert getattr(input_data, field_name) == at_limit

    @pytest.mark.parametrize("field_name", ["context", "additional_params"])
    def test_dict_over_key_limit_rejected(self, field_name):
        """Test that a dict above the key limit raises validation error (STIG V-222612)."""
        oversized = {f"k{i}": i for i in range(_limits.MAX_DICT_KEYS + 1)}
        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query="test", **{field_name: oversized})

        errors = exc_info.value.errors()
        assert errors[0]["loc"] == (field_name,)
        assert "keys" in errors[0]["msg"]

    @pytest.mark.parametrize("field_name", ["context", "additional_params"])
    def test_dict_over_byte_limit_rejected(self, field_name):
        """Test that a dict above the serialized size limit raises validation error (STIG V-222612)."""
        oversized = {"blob": "x" * _limits.MAX_DICT_BYTES}
        with pytest.raises(ValidationError) as exc_info:
            StrandsQueryTaskInput(query="test", **{field_name: oversized})

        errors = exc_info.value.errors()
        assert errors[0]["loc"] == (field_name,)
        assert "bytes" in errors[0]["msg"]

    def test_dict_key_over_length_limit_rejected(self):
        """Test that an over-long dict key raises validation error (STIG V-222612)."""
        with pytest.raises(ValidationError, match="key longer than"):
            StrandsQueryTaskInput(query="test", context={"k" * (_limits.MAX_DICT_KEY_LEN + 1): 1})

    def test_dict_bounds_enforced_on_model_validate(self):
        """Test that the worker-side model_validate path enforces dict bounds."""
        oversized = {f"k{i}": i for i in range(_limits.MAX_DICT_KEYS + 1)}
        with pytest.raises(ValidationError):
            StrandsQueryTaskInput.model_validate({"query": "test", "context": oversized})

    def test_model_serialization(self):
        """Test model can be serialized to dict."""
        input_data = StrandsQueryTaskInput(
            query="What are the features?",
            context={"source": "web"},
            session_id="sess-123",
            max_results=15,
            similarity_threshold=0.8,
            additional_params={"priority": "high"},
        )

        data_dict = input_data.model_dump()

        expected = {
            "query": "What are the features?",
            "context": {"source": "web"},
            "session_id": "sess-123",
            "max_results": 15,
            "similarity_threshold": 0.8,
            "additional_params": {"priority": "high"},
        }

        assert data_dict == expected

    def test_model_deserialization(self):
        """Test model can be created from dict."""
        data_dict = {
            "query": "What are the features?",
            "context": {"source": "web"},
            "session_id": "sess-123",
            "max_results": 15,
            "similarity_threshold": 0.8,
            "additional_params": {"priority": "high"},
        }

        input_data = StrandsQueryTaskInput(**data_dict)

        assert input_data.query == "What are the features?"
        assert input_data.context == {"source": "web"}
        assert input_data.session_id == "sess-123"
        assert input_data.max_results == 15
        assert input_data.similarity_threshold == 0.8
        assert input_data.additional_params == {"priority": "high"}

    def test_model_json_schema(self):
        """Test that model generates valid JSON schema."""
        schema = StrandsQueryTaskInput.model_json_schema()

        assert "properties" in schema
        assert "query" in schema["properties"]
        assert "context" in schema["properties"]
        assert "session_id" in schema["properties"]
        assert "max_results" in schema["properties"]
        assert "similarity_threshold" in schema["properties"]
        assert "additional_params" in schema["properties"]

        # Check required fields
        assert "required" in schema
        assert "query" in schema["required"]

        # Check field constraints
        query_props = schema["properties"]["query"]
        assert query_props["minLength"] == 1
        assert query_props["maxLength"] == _limits.MAX_TEXT_LEN

        max_results_props = schema["properties"]["max_results"]
        assert max_results_props["minimum"] == 1
        assert max_results_props["maximum"] == 100

        threshold_props = schema["properties"]["similarity_threshold"]
        assert threshold_props["minimum"] == 0.0
        assert threshold_props["maximum"] == 1.0
