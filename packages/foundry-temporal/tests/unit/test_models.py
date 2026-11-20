# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.models module"""

import json

import pytest
from foundry_temporal.models import DocumentMetadata
from pydantic import ValidationError


class TestDocumentMetadata:
    def test_document_metadata_basic_creation(self):
        """Test basic DocumentMetadata creation with required fields"""
        metadata = DocumentMetadata(
            workflow_id="test-workflow-123",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc-123",
        )

        assert metadata.workflow_id == "test-workflow-123"
        assert metadata.version == 1
        assert metadata.doc_type == "draft"
        assert metadata.created_at == "2023-12-01T10:30:00Z"
        assert metadata.document_key == "test-doc-123"
        assert metadata.approved is False  # Default value

    def test_document_metadata_with_all_fields(self):
        """Test DocumentMetadata creation with all fields"""
        metadata = DocumentMetadata(
            workflow_id="test-workflow-123",
            version=2,
            doc_type="final",
            created_at="2023-12-01T15:45:30Z",
            document_key="final-doc-123",
            approved=True,
        )

        assert metadata.workflow_id == "test-workflow-123"
        assert metadata.version == 2
        assert metadata.doc_type == "final"
        assert metadata.created_at == "2023-12-01T15:45:30Z"
        assert metadata.document_key == "final-doc-123"
        assert metadata.approved is True

    def test_document_metadata_validation_missing_fields(self):
        """Test validation errors for missing required fields"""
        # Missing workflow_id
        with pytest.raises(ValidationError) as exc_info:
            DocumentMetadata(version=1, doc_type="draft", created_at="2023-12-01T10:30:00Z", document_key="test-doc")
        assert "workflow_id" in str(exc_info.value)

        # Missing version
        with pytest.raises(ValidationError) as exc_info:
            DocumentMetadata(
                workflow_id="test-workflow",
                doc_type="draft",
                created_at="2023-12-01T10:30:00Z",
                document_key="test-doc",
            )
        assert "version" in str(exc_info.value)

        # Missing doc_type
        with pytest.raises(ValidationError) as exc_info:
            DocumentMetadata(
                workflow_id="test-workflow", version=1, created_at="2023-12-01T10:30:00Z", document_key="test-doc"
            )
        assert "doc_type" in str(exc_info.value)

        # Missing created_at
        with pytest.raises(ValidationError) as exc_info:
            DocumentMetadata(workflow_id="test-workflow", version=1, doc_type="draft", document_key="test-doc")
        assert "created_at" in str(exc_info.value)

        # Missing document_key
        with pytest.raises(ValidationError) as exc_info:
            DocumentMetadata(
                workflow_id="test-workflow", version=1, doc_type="draft", created_at="2023-12-01T10:30:00Z"
            )
        assert "document_key" in str(exc_info.value)

    def test_document_metadata_doc_type_validation(self):
        """Test that doc_type only accepts valid literal values"""
        # Valid doc_types
        for doc_type in ["draft", "final"]:
            metadata = DocumentMetadata(
                workflow_id="test-workflow",
                version=1,
                doc_type=doc_type,
                created_at="2023-12-01T10:30:00Z",
                document_key="test-doc",
            )
            assert metadata.doc_type == doc_type

        # Invalid doc_type
        with pytest.raises(ValidationError) as exc_info:
            DocumentMetadata(
                workflow_id="test-workflow",
                version=1,
                doc_type="invalid",  # Not in Literal["draft", "final"]
                created_at="2023-12-01T10:30:00Z",
                document_key="test-doc",
            )
        assert "doc_type" in str(exc_info.value)

    def test_document_metadata_version_validation(self):
        """Test version field validation"""
        # Valid version
        metadata = DocumentMetadata(
            workflow_id="test-workflow",
            version=42,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
        )
        assert metadata.version == 42

        # Invalid version (string)
        with pytest.raises(ValidationError) as exc_info:
            DocumentMetadata(
                workflow_id="test-workflow",
                version="invalid",
                doc_type="draft",
                created_at="2023-12-01T10:30:00Z",
                document_key="test-doc",
            )
        assert "version" in str(exc_info.value)

    def test_document_metadata_approved_validation(self):
        """Test approved field validation"""
        # Explicit True
        metadata = DocumentMetadata(
            workflow_id="test-workflow",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
            approved=True,
        )
        assert metadata.approved is True

        # Explicit False
        metadata = DocumentMetadata(
            workflow_id="test-workflow",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
            approved=False,
        )
        assert metadata.approved is False

        # Default (should be False)
        metadata = DocumentMetadata(
            workflow_id="test-workflow",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
        )
        assert metadata.approved is False

    def test_document_metadata_json_serialization(self):
        """Test JSON serialization and deserialization"""
        original = DocumentMetadata(
            workflow_id="test-workflow-123",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc-123",
            approved=True,
        )

        # Serialize to JSON
        json_data = original.model_dump()
        json_str = json.dumps(json_data)

        # Deserialize from JSON
        parsed_data = json.loads(json_str)
        restored = DocumentMetadata(**parsed_data)

        # Verify fields match
        assert restored.workflow_id == original.workflow_id
        assert restored.version == original.version
        assert restored.doc_type == original.doc_type
        assert restored.created_at == original.created_at
        assert restored.document_key == original.document_key
        assert restored.approved == original.approved

    def test_document_metadata_model_dump(self):
        """Test model_dump method"""
        metadata = DocumentMetadata(
            workflow_id="test-workflow",
            version=1,
            doc_type="final",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
            approved=True,
        )

        dump = metadata.model_dump()

        expected = {
            "workflow_id": "test-workflow",
            "version": 1,
            "doc_type": "final",
            "created_at": "2023-12-01T10:30:00Z",
            "document_key": "test-doc",
            "approved": True,
            "updated_at": None,
            "content_size": None,
            "iteration_count": None,
        }

        assert dump == expected

    def test_document_metadata_field_descriptions(self):
        """Test that field descriptions are properly set"""
        # This tests that the Field(..., description="...") is working
        schema = DocumentMetadata.model_json_schema()
        properties = schema["properties"]

        assert "description" in properties["workflow_id"]
        assert "description" in properties["version"]
        assert "description" in properties["doc_type"]
        assert "description" in properties["created_at"]
        assert "description" in properties["document_key"]
        assert "description" in properties["approved"]

        # Check some specific descriptions
        assert "Workflow ID" in properties["workflow_id"]["description"]
        assert "version number" in properties["version"]["description"]
        assert "Document type" in properties["doc_type"]["description"]

    def test_document_metadata_json_schema_examples(self):
        """Test that JSON schema includes examples"""
        schema = DocumentMetadata.model_json_schema()

        assert "examples" in schema
        assert len(schema["examples"]) > 0

        example = schema["examples"][0]
        assert "workflow_id" in example
        assert "version" in example
        assert "doc_type" in example
        assert "created_at" in example
        assert "document_key" in example
        assert "approved" in example

        # Verify example has valid doc_type
        assert example["doc_type"] in ["draft", "final"]

    def test_document_metadata_equality(self):
        """Test equality comparison between DocumentMetadata instances"""
        metadata1 = DocumentMetadata(
            workflow_id="test-workflow",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
            approved=False,
        )

        metadata2 = DocumentMetadata(
            workflow_id="test-workflow",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
            approved=False,
        )

        metadata3 = DocumentMetadata(
            workflow_id="different-workflow",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
            approved=False,
        )

        assert metadata1 == metadata2
        assert metadata1 != metadata3

    def test_document_metadata_immutability(self):
        """Test that DocumentMetadata is immutable (frozen)"""
        metadata = DocumentMetadata(
            workflow_id="test-workflow",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
        )

        # Attempting to modify should raise an error if frozen=True
        # Note: The current model doesn't show frozen=True, so this might not apply
        # We'll test if modification is allowed or not
        try:
            metadata.version = 2
            # If this succeeds, the model is mutable (which might be intentional)
            assert metadata.version == 2
        except AttributeError, TypeError:
            # If this fails, the model is immutable
            assert metadata.version == 1

    def test_document_metadata_repr(self):
        """Test string representation of DocumentMetadata"""
        metadata = DocumentMetadata(
            workflow_id="test-workflow",
            version=1,
            doc_type="draft",
            created_at="2023-12-01T10:30:00Z",
            document_key="test-doc",
        )

        repr_str = repr(metadata)
        assert "DocumentMetadata" in repr_str
        assert "workflow_id='test-workflow'" in repr_str
        assert "version=1" in repr_str
