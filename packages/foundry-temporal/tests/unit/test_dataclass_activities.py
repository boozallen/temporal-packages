# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.dataclass_activities module"""

from dataclasses import dataclass

import pytest
from foundry_temporal.activities import ActivityConfig
from foundry_temporal.dataclass_activities import (
    APICallInput,
    BasicTaskInput,
    BatchProcessingInput,
    FileProcessingInput,
    dataclass_activity,
    dataclass_to_dict,
    dict_to_dataclass,
    validate_dataclass_input,
)
from foundry_temporal.errors import NonRetryableError, RetryableError


class TestDataclassActivity:
    """Tests for the dataclass_activity decorator"""

    def test_decorator_basic_application(self):
        """Test basic decorator application"""

        @dataclass_activity()
        async def test_activity(input_data: BasicTaskInput) -> str:
            return f"Processed: {input_data.query}"

        assert callable(test_activity)

    def test_decorator_with_custom_config(self):
        """Test decorator with custom configuration"""
        config = ActivityConfig(enable_observability=True, log_inputs=True)

        @dataclass_activity(config=config)
        async def test_activity(input_data: BasicTaskInput) -> str:
            return "success"

        assert callable(test_activity)

    def test_decorator_with_custom_name(self):
        """Test decorator with custom activity name"""

        @dataclass_activity(name="custom_activity_name")
        async def test_activity(input_data: BasicTaskInput) -> str:
            return "success"

        assert callable(test_activity)

    @pytest.mark.asyncio
    async def test_dataclass_activity_execution_basic(self):
        """Test basic dataclass activity execution"""

        @dataclass_activity()
        async def test_activity(input_data: BasicTaskInput) -> str:
            return f"Processed: {input_data.query}"

        input_data = BasicTaskInput(query="test query", timeout=30)
        result = await test_activity(input_data)

        assert result == "Processed: test query"

    @pytest.mark.asyncio
    async def test_dataclass_activity_with_error_handling_retryable(self):
        """Test dataclass activity error handling for retryable errors"""

        @dataclass_activity()
        async def test_activity(input_data: BasicTaskInput) -> str:
            raise ConnectionError("Network timeout")

        input_data = BasicTaskInput(query="test")

        with pytest.raises(RetryableError):
            await test_activity(input_data)

    @pytest.mark.asyncio
    async def test_dataclass_activity_with_error_handling_non_retryable(self):
        """Test dataclass activity error handling for non-retryable errors"""

        @dataclass_activity()
        async def test_activity(input_data: BasicTaskInput) -> str:
            raise ValueError("Invalid input")

        input_data = BasicTaskInput(query="test")

        with pytest.raises(NonRetryableError):
            await test_activity(input_data)

    @pytest.mark.asyncio
    async def test_dataclass_activity_with_custom_input_type(self):
        """Test dataclass activity with custom input dataclass"""

        @dataclass
        class CustomInput:
            name: str
            age: int

        @dataclass_activity()
        async def test_activity(input_data: CustomInput) -> dict:
            return {"name": input_data.name, "age": input_data.age}

        input_data = CustomInput(name="John", age=30)
        result = await test_activity(input_data)

        assert result == {"name": "John", "age": 30}

    @pytest.mark.asyncio
    async def test_dataclass_activity_with_complex_return(self):
        """Test dataclass activity with complex return types"""

        @dataclass
        class ComplexOutput:
            status: str
            data: list[str]

        @dataclass_activity()
        async def test_activity(input_data: BasicTaskInput) -> ComplexOutput:
            return ComplexOutput(status="success", data=["item1", "item2"])

        input_data = BasicTaskInput(query="test")
        result = await test_activity(input_data)

        assert result.status == "success"
        assert result.data == ["item1", "item2"]

    @pytest.mark.asyncio
    async def test_dataclass_activity_with_disabled_error_wrapping(self):
        """Test dataclass activity with disabled error wrapping"""
        config = ActivityConfig(enable_error_wrapping=False)

        @dataclass_activity(config=config)
        async def test_activity(input_data: BasicTaskInput) -> str:
            raise ValueError("Original error")

        input_data = BasicTaskInput(query="test")

        # Should raise original error, not wrapped
        with pytest.raises(ValueError, match="Original error"):
            await test_activity(input_data)


class TestValidateDataclassInput:
    """Tests for validate_dataclass_input function"""

    def test_validate_correct_type(self):
        """Test validation with correct dataclass type"""
        input_data = BasicTaskInput(query="test")
        # Should not raise
        validate_dataclass_input(input_data, BasicTaskInput)

    def test_validate_incorrect_type(self):
        """Test validation with incorrect type"""
        input_data = FileProcessingInput(file_path="/test.txt", operation="read")

        with pytest.raises(TypeError, match="Expected BasicTaskInput"):
            validate_dataclass_input(input_data, BasicTaskInput)

    def test_validate_non_dataclass(self):
        """Test validation with non-dataclass type"""
        input_data = "not a dataclass"

        with pytest.raises(TypeError):
            validate_dataclass_input(input_data, BasicTaskInput)


class TestDataclassToDict:
    """Tests for dataclass_to_dict function"""

    def test_basic_conversion(self):
        """Test basic dataclass to dict conversion"""
        input_obj = BasicTaskInput(query="test query", timeout=60)
        result = dataclass_to_dict(input_obj)

        assert result == {"query": "test query", "timeout": 60, "metadata": None}

    def test_conversion_with_none_values(self):
        """Test conversion with None values"""
        input_obj = BasicTaskInput(query="test", metadata=None)
        result = dataclass_to_dict(input_obj)

        assert result["metadata"] is None

    def test_conversion_with_complex_types(self):
        """Test conversion with complex types"""
        input_obj = FileProcessingInput(file_path="/test.txt", operation="read", options={"format": "json"})
        result = dataclass_to_dict(input_obj)

        assert result["file_path"] == "/test.txt"
        assert result["operation"] == "read"
        assert result["options"] == {"format": "json"}
        assert result["output_format"] == "json"


class TestDictToDataclass:
    """Tests for dict_to_dataclass function"""

    def test_basic_conversion(self):
        """Test basic dict to dataclass conversion"""
        data = {"query": "test query", "timeout": 60}
        result = dict_to_dataclass(data, BasicTaskInput)

        assert isinstance(result, BasicTaskInput)
        assert result.query == "test query"
        assert result.timeout == 60

    def test_conversion_with_defaults(self):
        """Test conversion with default values"""
        data = {"query": "test"}
        result = dict_to_dataclass(data, BasicTaskInput)

        assert result.query == "test"
        assert result.timeout == 30  # default value
        assert result.metadata is None

    def test_conversion_with_extra_fields(self):
        """Test conversion with extra fields in dict"""
        data = {"query": "test", "timeout": 60, "extra_field": "ignored"}
        result = dict_to_dataclass(data, BasicTaskInput)

        assert result.query == "test"
        assert result.timeout == 60
        assert not hasattr(result, "extra_field")

    def test_conversion_invalid_dataclass_type(self):
        """Test conversion with invalid dataclass type"""
        data = {"query": "test"}

        with pytest.raises(TypeError, match="is not a dataclass"):
            dict_to_dataclass(data, str)

    def test_conversion_with_complex_types(self):
        """Test conversion with complex types"""
        data = {
            "items": ["a", "b", "c"],
            "batch_size": 50,
            "concurrent": True,
            "options": {"sort": "ascending"},
        }
        result = dict_to_dataclass(data, BatchProcessingInput)

        assert result.items == ["a", "b", "c"]
        assert result.batch_size == 50
        assert result.concurrent is True
        assert result.options == {"sort": "ascending"}


class TestPredefinedInputModels:
    """Tests for pre-defined input models"""

    def test_basic_task_input(self):
        """Test BasicTaskInput model"""
        input_obj = BasicTaskInput(query="test query", timeout=45, metadata={"key": "value"})

        assert input_obj.query == "test query"
        assert input_obj.timeout == 45
        assert input_obj.metadata == {"key": "value"}

    def test_file_processing_input(self):
        """Test FileProcessingInput model"""
        input_obj = FileProcessingInput(file_path="/data/file.txt", operation="parse", options={"encoding": "utf-8"})

        assert input_obj.file_path == "/data/file.txt"
        assert input_obj.operation == "parse"
        assert input_obj.output_format == "json"
        assert input_obj.options == {"encoding": "utf-8"}

    def test_batch_processing_input(self):
        """Test BatchProcessingInput model"""
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        input_obj = BatchProcessingInput(items=items, batch_size=2, concurrent=False)

        assert input_obj.items == items
        assert input_obj.batch_size == 2
        assert input_obj.concurrent is False

    def test_api_call_input(self):
        """Test APICallInput model"""
        input_obj = APICallInput(
            endpoint="https://api.example.com/users",
            method="POST",
            headers={"Authorization": "Bearer token"},
            body={"name": "test"},
            timeout=60,
            retries=5,
        )

        assert input_obj.endpoint == "https://api.example.com/users"
        assert input_obj.method == "POST"
        assert input_obj.headers == {"Authorization": "Bearer token"}
        assert input_obj.body == {"name": "test"}
        assert input_obj.timeout == 60
        assert input_obj.retries == 5

    def test_api_call_input_defaults(self):
        """Test APICallInput with defaults"""
        input_obj = APICallInput(endpoint="https://api.example.com")

        assert input_obj.method == "GET"
        assert input_obj.timeout == 30
        assert input_obj.retries == 3


class TestDataclassActivityImports:
    """Tests for dataclass activity imports from package"""

    def test_dataclass_activity_available(self):
        """Test dataclass_activity is available from foundry_temporal"""
        from foundry_temporal import dataclass_activity as decorator

        assert callable(decorator)

    def test_input_models_available(self):
        """Test input models are available from foundry_temporal"""
        from foundry_temporal import (
            APICallInput,
            BasicTaskInput,
            BatchProcessingInput,
            FileProcessingInput,
        )

        assert callable(BasicTaskInput)
        assert callable(FileProcessingInput)
        assert callable(BatchProcessingInput)
        assert callable(APICallInput)

    def test_utility_functions_available(self):
        """Test utility functions are available from foundry_temporal"""
        from foundry_temporal import (
            dataclass_to_dict,
            dict_to_dataclass,
            validate_dataclass_input,
        )

        assert callable(dataclass_to_dict)
        assert callable(dict_to_dataclass)
        assert callable(validate_dataclass_input)
