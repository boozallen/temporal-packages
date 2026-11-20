# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.queries module"""

from datetime import datetime
from unittest.mock import patch

from foundry_temporal.queries import QueryMixin


class TestQueryMixin:
    def test_init_default_attributes(self):
        """Test QueryMixin initialization with default attributes"""
        mixin = QueryMixin()

        # Should set default values if attributes don't exist
        assert mixin.workflow_id == "unknown"
        assert mixin.current_phase == "initializing"

    def test_init_preserves_existing_attributes(self):
        """Test QueryMixin preserves existing attributes"""

        class TestClass(QueryMixin):
            def __init__(self):
                self.workflow_id = "existing-workflow"
                self.current_phase = "existing-phase"
                super().__init__()

        instance = TestClass()

        # Should preserve existing values
        assert instance.workflow_id == "existing-workflow"
        assert instance.current_phase == "existing-phase"

    def test_init_partial_existing_attributes(self):
        """Test QueryMixin with only some existing attributes"""

        class TestClass(QueryMixin):
            def __init__(self):
                self.workflow_id = "existing-workflow"
                # current_phase not set
                super().__init__()

        instance = TestClass()

        # Should preserve existing and set default for missing
        assert instance.workflow_id == "existing-workflow"
        assert instance.current_phase == "initializing"

    @patch("foundry_temporal.queries.workflow.now")
    def test_get_status_basic(self, mock_now):
        """Test basic get_status functionality"""
        # Mock workflow.now() to return a fixed datetime
        mock_datetime = datetime(2023, 12, 1, 10, 30, 0)
        mock_now.return_value = mock_datetime

        mixin = QueryMixin()
        status = mixin.get_status()

        expected_status = {
            "workflow_id": "unknown",
            "current_phase": "initializing",
            "iteration": 0,
            "approved": False,
            "approved_by": None,
            "plan_approved_by": None,
            "document_approved_by": None,
            "awaiting_feedback": False,
            "current_document_key": None,
            "last_updated": "2023-12-01T10:30:00",
        }

        assert status == expected_status
        mock_now.assert_called_once()

    @patch("foundry_temporal.queries.workflow.now")
    def test_get_status_with_custom_attributes(self, mock_now):
        """Test get_status with custom attribute values"""
        mock_datetime = datetime(2023, 12, 1, 15, 45, 30)
        mock_now.return_value = mock_datetime

        class TestWorkflow(QueryMixin):
            def __init__(self):
                self.workflow_id = "test-workflow-123"
                self.current_phase = "research_execution"
                self.iteration = 3
                self.approved = True
                self.approved_by = "jane.doe@example.com"
                self.plan_approved_by = "john.smith@example.com"
                self.document_approved_by = "jane.doe@example.com"
                self.awaiting_feedback = True
                self.current_document_key = "doc-key-456"
                super().__init__()

        workflow = TestWorkflow()
        status = workflow.get_status()

        expected_status = {
            "workflow_id": "test-workflow-123",
            "current_phase": "research_execution",
            "iteration": 3,
            "approved": True,
            "approved_by": "jane.doe@example.com",
            "plan_approved_by": "john.smith@example.com",
            "document_approved_by": "jane.doe@example.com",
            "awaiting_feedback": True,
            "current_document_key": "doc-key-456",
            "last_updated": "2023-12-01T15:45:30",
        }

        assert status == expected_status

    @patch("foundry_temporal.queries.workflow.now")
    def test_get_status_missing_attributes_use_defaults(self, mock_now):
        """Test get_status uses default values for missing attributes"""
        mock_datetime = datetime(2023, 12, 1, 12, 0, 0)
        mock_now.return_value = mock_datetime

        class TestWorkflow(QueryMixin):
            def __init__(self):
                # Only set some attributes
                self.workflow_id = "partial-workflow"
                self.current_phase = "planning"
                # iteration, approved, approved_by, plan_approved_by,
                # document_approved_by, awaiting_feedback,
                # current_document_key not set
                super().__init__()

        workflow = TestWorkflow()
        status = workflow.get_status()

        # Should use defaults for missing attributes
        assert status["workflow_id"] == "partial-workflow"
        assert status["current_phase"] == "planning"
        assert status["iteration"] == 0  # default
        assert status["approved"] is False  # default
        assert status["approved_by"] is None  # default
        assert status["plan_approved_by"] is None  # default
        assert status["document_approved_by"] is None  # default
        assert status["awaiting_feedback"] is False  # default
        assert status["current_document_key"] is None  # default
        assert status["last_updated"] == "2023-12-01T12:00:00"

    @patch("foundry_temporal.queries.workflow.now")
    def test_get_status_attribute_types(self, mock_now):
        """Test get_status with various attribute types"""
        mock_datetime = datetime(2023, 12, 1, 9, 15, 45)
        mock_now.return_value = mock_datetime

        class TestWorkflow(QueryMixin):
            def __init__(self):
                self.workflow_id = "type-test-workflow"
                self.current_phase = "testing"
                self.iteration = "5"  # String instead of int
                self.approved = "yes"  # String instead of bool
                self.approved_by = 42  # Int instead of string
                self.plan_approved_by = 43  # Int instead of string
                self.document_approved_by = 44  # Int instead of string
                self.awaiting_feedback = 1  # Int instead of bool
                self.current_document_key = 12345  # Int instead of string
                super().__init__()

        workflow = TestWorkflow()
        status = workflow.get_status()

        # Should preserve actual values (no type conversion)
        assert status["iteration"] == "5"
        assert status["approved"] == "yes"
        assert status["approved_by"] == 42
        assert status["plan_approved_by"] == 43
        assert status["document_approved_by"] == 44
        assert status["awaiting_feedback"] == 1
        assert status["current_document_key"] == 12345

    def test_get_status_is_workflow_query(self):
        """Test that get_status method has workflow.query decorator"""
        # Check that get_status is decorated with workflow.query
        assert hasattr(QueryMixin.get_status, "__temporal_query_definition")

    @patch("foundry_temporal.queries.workflow.now")
    def test_get_status_returns_dict(self, mock_now):
        """Test that get_status always returns a dictionary"""
        mock_now.return_value = datetime(2023, 12, 1, 10, 0, 0)

        mixin = QueryMixin()
        status = mixin.get_status()

        assert isinstance(status, dict)
        assert len(status) == 10  # Should have exactly 10 keys

    @patch("foundry_temporal.queries.workflow.now")
    def test_get_status_required_keys(self, mock_now):
        """Test that get_status always includes required keys"""
        mock_now.return_value = datetime(2023, 12, 1, 10, 0, 0)

        mixin = QueryMixin()
        status = mixin.get_status()

        required_keys = [
            "workflow_id",
            "current_phase",
            "iteration",
            "approved",
            "approved_by",
            "plan_approved_by",
            "document_approved_by",
            "awaiting_feedback",
            "current_document_key",
            "last_updated",
        ]

        for key in required_keys:
            assert key in status, f"Missing required key: {key}"

    @patch("foundry_temporal.queries.workflow.now")
    def test_get_status_last_updated_format(self, mock_now):
        """Test that last_updated is properly formatted as ISO string"""
        mock_datetime = datetime(2023, 12, 1, 14, 30, 45, 123456)
        mock_now.return_value = mock_datetime

        mixin = QueryMixin()
        status = mixin.get_status()

        # Should be ISO format string
        assert status["last_updated"] == "2023-12-01T14:30:45.123456"
        assert isinstance(status["last_updated"], str)

    def test_mixin_with_multiple_inheritance(self):
        """Test QueryMixin works with multiple inheritance"""

        class BaseWorkflow:
            def __init__(self):
                self.base_initialized = True

        class TestWorkflow(QueryMixin, BaseWorkflow):
            def __init__(self):
                BaseWorkflow.__init__(self)  # Call base first
                QueryMixin.__init__(self)  # Then mixin

        workflow = TestWorkflow()

        # Should have both base and mixin functionality
        assert workflow.base_initialized is True
        assert hasattr(workflow, "workflow_id")
        assert hasattr(workflow, "get_status")

    def test_multiple_get_status_calls_consistent(self):
        """Test that multiple calls to get_status are consistent"""

        class TestWorkflow(QueryMixin):
            def __init__(self):
                self.workflow_id = "consistent-test"
                self.current_phase = "testing"
                self.iteration = 1
                super().__init__()

        workflow = TestWorkflow()

        with patch("foundry_temporal.queries.workflow.now") as mock_now:
            mock_datetime = datetime(2023, 12, 1, 10, 0, 0)
            mock_now.return_value = mock_datetime

            status1 = workflow.get_status()
            status2 = workflow.get_status()

            # Should be identical except potentially last_updated
            assert status1["workflow_id"] == status2["workflow_id"]
            assert status1["current_phase"] == status2["current_phase"]
            assert status1["iteration"] == status2["iteration"]

    @patch("foundry_temporal.queries.workflow.now")
    def test_get_status_none_values(self, mock_now):
        """Test get_status handles None values correctly"""
        mock_now.return_value = datetime(2023, 12, 1, 10, 0, 0)

        class TestWorkflow(QueryMixin):
            def __init__(self):
                self.workflow_id = None
                self.current_phase = None
                self.iteration = None
                self.approved = None
                self.awaiting_feedback = None
                self.current_document_key = None
                super().__init__()

        workflow = TestWorkflow()
        status = workflow.get_status()

        # getattr with defaults should still provide fallbacks for None
        # But getattr(obj, 'attr', default) returns None if attr exists and is None
        assert status["workflow_id"] is None
        assert status["current_phase"] is None
        assert status["iteration"] is None
        assert status["approved"] is None
        assert status["awaiting_feedback"] is None
        assert status["current_document_key"] is None

    def test_init_doesnt_overwrite_falsy_values(self):
        """Test that __init__ doesn't overwrite falsy but valid values"""

        class TestClass(QueryMixin):
            def __init__(self):
                self.workflow_id = ""  # Empty string (falsy but valid)
                self.current_phase = ""  # Empty string (falsy but valid)
                super().__init__()

        instance = TestClass()

        # Should preserve empty strings, not replace with defaults
        assert instance.workflow_id == ""
        assert instance.current_phase == ""
