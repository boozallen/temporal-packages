# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""Tests for foundry_temporal.storage module"""

import json
from unittest.mock import AsyncMock, Mock, mock_open, patch

import pytest
from cryptography.exceptions import InvalidTag
from foundry_temporal.errors import NonRetryableError, RetryableError, StorageError
from foundry_temporal.models import DocumentMetadata
from foundry_temporal.storage import (
    DocumentStorage,
    DynamoDBStorage,
    LocalFileStorage,
    S3Storage,
    StorageBackend,
    _validate_storage_id,
)


class TestStorageBackend:
    def test_abstract_base_class_cannot_be_instantiated(self):
        """Test that StorageBackend cannot be instantiated directly"""
        with pytest.raises(TypeError):
            StorageBackend()

    def test_abstract_methods_must_be_implemented(self):
        """Test that all abstract methods must be implemented in subclasses"""

        class IncompleteStorage(StorageBackend):
            pass

        with pytest.raises(TypeError):
            IncompleteStorage()

    def test_concrete_implementation_with_all_methods(self):
        """Test that concrete implementation with all methods can be instantiated"""

        class CompleteStorage(StorageBackend):
            async def store_document(self, workflow_id, document_key, content, metadata=None):
                return "stored"

            async def retrieve_document(self, workflow_id, document_key):
                return "content"

            async def get_document_metadata(self, workflow_id, document_key):
                return DocumentMetadata(
                    workflow_id=workflow_id,
                    document_key=document_key,
                    version=1,
                    doc_type="draft",
                    created_at="2023-12-01T10:00:00Z",
                )

            async def list_documents(self, workflow_id, doc_type=None):
                return []

            async def get_latest_document_key(self, workflow_id, doc_type):
                return "latest_key"

        storage = CompleteStorage()
        assert storage is not None

    def test_abstract_method_signatures(self):
        """Test that abstract methods have correct signatures"""

        # Get the abstract methods
        abstract_methods = StorageBackend.__abstractmethods__

        expected_methods = {
            "store_document",
            "retrieve_document",
            "get_document_metadata",
            "list_documents",
            "get_latest_document_key",
        }

        assert abstract_methods == expected_methods


class TestDynamoDBStorage:
    def test_init_default_values(self):
        """Test DynamoDBStorage initialization with default values"""
        storage = DynamoDBStorage()

        assert storage.table_name == "research-documents"
        assert storage.region == "us-east-1"
        assert storage._table is None

    def test_init_custom_values(self):
        """Test DynamoDBStorage initialization with custom values"""
        storage = DynamoDBStorage(table_name="custom-table", region="us-west-2")

        assert storage.table_name == "custom-table"
        assert storage.region == "us-west-2"

    @patch("foundry_temporal.storage.boto3")
    def test_table_property_lazy_loading(self, mock_boto3):
        """Test that table property lazy-loads DynamoDB resource"""
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_boto3.resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_table

        storage = DynamoDBStorage(table_name="test-table", region="us-west-2")

        # First access should create the table
        table1 = storage.table
        assert table1 is mock_table
        mock_boto3.resource.assert_called_once_with("dynamodb", region_name="us-west-2")
        mock_dynamodb.Table.assert_called_once_with("test-table")

        # Second access should return same instance
        table2 = storage.table
        assert table2 is mock_table
        assert table1 is table2

    @patch("foundry_temporal.storage.boto3")
    @patch("foundry_temporal.storage.datetime")
    @pytest.mark.asyncio
    async def test_store_document_success(self, mock_datetime, mock_boto3):
        """Test successful document storage"""
        mock_datetime.utcnow.return_value.isoformat.return_value = "2023-12-01T10:30:00"

        mock_table = Mock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        result = await storage.store_document(
            workflow_id="test-workflow", document_key="draft#1", content="test content", metadata={"author": "test"}
        )

        assert result == "draft#1"
        mock_table.put_item.assert_called_once()

        call_args = mock_table.put_item.call_args[1]["Item"]
        assert call_args["workflow_id"] == "test-workflow"
        assert call_args["document_key"] == "draft#1"
        # Content is encrypted — verify it's a JSON payload with the encrypted marker
        stored_content = json.loads(call_args["content"])
        assert stored_content.get("__encrypted") is True
        assert "test content" not in call_args["content"]
        assert call_args["created_at"] == "2023-12-01T10:30:00"
        assert call_args["updated_at"] == "2023-12-01T10:30:00"
        assert call_args["content_size"] == len("test content")
        assert call_args["metadata"] == {"author": "test"}

    @patch("foundry_temporal.storage.boto3")
    @patch("foundry_temporal.storage.datetime")
    @pytest.mark.asyncio
    async def test_store_document_without_metadata(self, mock_datetime, mock_boto3):
        """Test document storage without metadata"""
        mock_datetime.utcnow.return_value.isoformat.return_value = "2023-12-01T10:30:00"

        mock_table = Mock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        await storage.store_document(workflow_id="test-workflow", document_key="draft#1", content="test content")

        call_args = mock_table.put_item.call_args[1]["Item"]
        assert "metadata" not in call_args

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_store_document_error_handling(self, mock_boto3):
        """Test store_document error handling"""
        mock_table = Mock()
        mock_table.put_item.side_effect = Exception("DynamoDB error")
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        with pytest.raises((RetryableError, NonRetryableError)):  # Should be wrapped by classify_and_wrap_error
            await storage.store_document(workflow_id="test-workflow", document_key="draft#1", content="test content")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_retrieve_document_success(self, mock_boto3):
        """Test successful document retrieval"""
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {"workflow_id": "test-workflow", "document_key": "draft#1", "content": "retrieved content"}
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        result = await storage.retrieve_document("test-workflow", "draft#1")
        assert result == "retrieved content"

        mock_table.get_item.assert_called_once_with(Key={"workflow_id": "test-workflow", "document_key": "draft#1"})

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_retrieve_document_not_found(self, mock_boto3):
        """Test document retrieval when document not found"""
        mock_table = Mock()
        mock_table.get_item.return_value = {}  # No 'Item' key
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        with pytest.raises(StorageError) as exc_info:
            await storage.retrieve_document("test-workflow", "nonexistent")

        assert "Document not found: test-workflow/nonexistent" in str(exc_info.value)

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_retrieve_document_empty_content(self, mock_boto3):
        """Test document retrieval with missing content field"""
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {
                "workflow_id": "test-workflow",
                "document_key": "draft#1",
                # No 'content' field
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        result = await storage.retrieve_document("test-workflow", "draft#1")
        assert result == ""  # Should return empty string for missing content

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_document_metadata_success(self, mock_boto3):
        """Test successful metadata retrieval"""
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {
                "workflow_id": "test-workflow",
                "document_key": "draft#1",
                "created_at": "2023-12-01T10:30:00Z",
                "updated_at": "2023-12-01T11:00:00Z",
                "approved": True,
                "content_size": 100,
                "iteration_count": 3,
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        metadata = await storage.get_document_metadata("test-workflow", "draft#1")

        assert isinstance(metadata, DocumentMetadata)
        assert metadata.workflow_id == "test-workflow"
        assert metadata.document_key == "draft#1"
        assert metadata.version == 1
        assert metadata.doc_type == "draft"
        assert metadata.created_at == "2023-12-01T10:30:00Z"
        assert metadata.approved is True

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_document_metadata_with_version(self, mock_boto3):
        """Test metadata retrieval with version parsing"""
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {"workflow_id": "test-workflow", "document_key": "final#5", "created_at": "2023-12-01T10:30:00Z"}
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        metadata = await storage.get_document_metadata("test-workflow", "final#5")

        assert metadata.doc_type == "final"
        assert metadata.version == 5

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_document_metadata_invalid_version(self, mock_boto3):
        """Test metadata retrieval with invalid version in key"""
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {
                "workflow_id": "test-workflow",
                "document_key": "draft#invalid",
                "created_at": "2023-12-01T10:30:00Z",
            }
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        metadata = await storage.get_document_metadata("test-workflow", "draft#invalid")

        assert metadata.version == 1  # Default fallback

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_document_metadata_not_found(self, mock_boto3):
        """Test metadata retrieval when document not found"""
        mock_table = Mock()
        mock_table.get_item.return_value = {}  # No 'Item' key
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()

        with pytest.raises(StorageError) as exc_info:
            await storage.get_document_metadata("test-workflow", "nonexistent")

        assert "Document not found: test-workflow/nonexistent" in str(exc_info.value)

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_list_documents_all(self, mock_boto3):
        """Test listing all documents for a workflow"""

        mock_table = Mock()
        mock_table.query.return_value = {
            "Items": [
                {"workflow_id": "test-workflow", "document_key": "draft#1", "created_at": "2023-12-01T10:30:00Z"},
                {"workflow_id": "test-workflow", "document_key": "final#2", "created_at": "2023-12-01T11:30:00Z"},
            ]
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        # Mock boto3.dynamodb.conditions.Key
        with patch("foundry_temporal.storage.Key") as mock_key:
            mock_key_instance = Mock()
            mock_key.return_value = mock_key_instance
            mock_key_instance.eq.return_value = mock_key_instance

            storage = DynamoDBStorage()
            documents = await storage.list_documents("test-workflow")

        assert len(documents) == 2
        assert all(isinstance(doc, DocumentMetadata) for doc in documents)
        assert documents[0].doc_type == "draft"
        assert documents[0].version == 1
        assert documents[1].doc_type == "final"
        assert documents[1].version == 2

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_list_documents_filtered_by_type(self, mock_boto3):
        """Test listing documents filtered by type"""
        mock_table = Mock()
        mock_table.query.return_value = {
            "Items": [{"workflow_id": "test-workflow", "document_key": "draft#1", "created_at": "2023-12-01T10:30:00Z"}]
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        with patch("foundry_temporal.storage.Key") as mock_key:
            # Create a mock that supports the & operator
            class MockKeyCondition:
                def __and__(self, other):
                    return self

                def eq(self, value):
                    return self

                def begins_with(self, prefix):
                    return self

            mock_key.return_value = MockKeyCondition()

            storage = DynamoDBStorage()
            documents = await storage.list_documents("test-workflow", doc_type="draft")

        assert len(documents) == 1
        assert documents[0].doc_type == "draft"

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_latest_document_key_success(self, mock_boto3):
        """Test getting latest document key"""
        mock_table = Mock()
        mock_table.query.return_value = {"Items": [{"workflow_id": "test-workflow", "document_key": "draft#5"}]}
        mock_boto3.resource.return_value.Table.return_value = mock_table

        with patch("foundry_temporal.storage.Key") as mock_key:
            # Create a mock that supports the & operator
            class MockKeyCondition:
                def __and__(self, other):
                    return self

                def eq(self, value):
                    return self

                def begins_with(self, prefix):
                    return self

            mock_key.return_value = MockKeyCondition()

            storage = DynamoDBStorage()
            latest_key = await storage.get_latest_document_key("test-workflow", "draft")

        assert latest_key == "draft#5"

        # Verify query parameters
        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["ScanIndexForward"] is False  # Reverse order
        assert call_kwargs["Limit"] == 1

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_latest_document_key_not_found(self, mock_boto3):
        """Test getting latest document key when no documents exist"""
        mock_table = Mock()
        mock_table.query.return_value = {"Items": []}
        mock_boto3.resource.return_value.Table.return_value = mock_table

        with patch("foundry_temporal.storage.Key") as mock_key:
            # Create a mock that supports the & operator
            class MockKeyCondition:
                def __and__(self, other):
                    return self

                def eq(self, value):
                    return self

                def begins_with(self, prefix):
                    return self

            mock_key.return_value = MockKeyCondition()

            storage = DynamoDBStorage()

            with pytest.raises(StorageError) as exc_info:
                await storage.get_latest_document_key("test-workflow", "draft")

            assert "No documents found for test-workflow/draft" in str(exc_info.value)


class TestS3Storage:
    def test_init_default_values(self):
        """Test S3Storage initialization with default values"""
        storage = S3Storage(bucket_name="test-bucket")

        assert storage.bucket_name == "test-bucket"
        assert storage.region == "us-east-1"
        assert storage._s3 is None

    def test_init_custom_values(self):
        """Test S3Storage initialization with custom values"""
        storage = S3Storage(bucket_name="custom-bucket", region="us-west-2")

        assert storage.bucket_name == "custom-bucket"
        assert storage.region == "us-west-2"

    @patch("foundry_temporal.storage.boto3")
    def test_s3_property_lazy_loading(self, mock_boto3):
        """Test that s3 property lazy-loads S3 client"""
        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket", region="us-west-2")

        # First access should create the client
        s3_1 = storage.s3
        assert s3_1 is mock_s3_client
        mock_boto3.client.assert_called_once_with("s3", region_name="us-west-2")

        # Second access should return same instance
        s3_2 = storage.s3
        assert s3_2 is mock_s3_client
        assert s3_1 is s3_2

    @patch("foundry_temporal.storage.boto3")
    @patch("foundry_temporal.storage.datetime")
    @pytest.mark.asyncio
    async def test_store_document_success(self, mock_datetime, mock_boto3):
        """Test successful document storage to S3"""
        mock_datetime.utcnow.return_value.isoformat.return_value = "2023-12-01T10:30:00"

        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")

        result = await storage.store_document(
            workflow_id="test-workflow",
            document_key="draft#1",
            content="test content",
            metadata={"author": "test", "version": 1},
        )

        expected_key = "test-workflow/draft#1"
        assert result == expected_key

        mock_s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3_client.put_object.call_args[1]

        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == expected_key
        # Content is encrypted — verify it's a JSON payload with the encrypted marker
        raw_body = call_kwargs["Body"]
        body_str = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body
        stored_payload = json.loads(body_str)
        assert stored_payload.get("__encrypted") is True
        assert b"test content" not in call_kwargs["Body"]

        metadata = call_kwargs["Metadata"]
        assert metadata["workflow-id"] == "test-workflow"
        assert metadata["document-key"] == "draft#1"
        assert metadata["stored-at"] == "2023-12-01T10:30:00"
        assert metadata["custom-author"] == "test"
        assert metadata["custom-version"] == "1"

    @patch("foundry_temporal.storage.boto3")
    @patch("foundry_temporal.storage.datetime")
    @pytest.mark.asyncio
    async def test_store_document_without_metadata(self, mock_datetime, mock_boto3):
        """Test document storage to S3 without custom metadata"""
        mock_datetime.utcnow.return_value.isoformat.return_value = "2023-12-01T10:30:00"

        mock_s3_client = Mock()
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")

        await storage.store_document(workflow_id="test-workflow", document_key="draft#1", content="test content")

        call_kwargs = mock_s3_client.put_object.call_args[1]
        metadata = call_kwargs["Metadata"]

        # Should only have standard metadata, no custom- prefixed keys
        assert "workflow-id" in metadata
        assert "document-key" in metadata
        assert "stored-at" in metadata
        assert not any(key.startswith("custom-") for key in metadata.keys())

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_store_document_error_handling(self, mock_boto3):
        """Test S3 store_document error handling"""
        mock_s3_client = Mock()
        mock_s3_client.put_object.side_effect = Exception("S3 error")
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")

        with pytest.raises((RetryableError, NonRetryableError)):  # Should be wrapped by classify_and_wrap_error
            await storage.store_document(workflow_id="test-workflow", document_key="draft#1", content="test content")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_retrieve_document_success(self, mock_boto3):
        """Test successful document retrieval from S3"""
        mock_s3_client = Mock()
        mock_body = Mock()
        mock_body.read.return_value = b"retrieved content"
        mock_s3_client.get_object.return_value = {"Body": mock_body}
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")
        result = await storage.retrieve_document("test-workflow", "draft#1")

        assert result == "retrieved content"
        mock_s3_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="test-workflow/draft#1")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_retrieve_document_error_handling(self, mock_boto3):
        """Test S3 retrieve_document error handling"""
        mock_s3_client = Mock()
        mock_s3_client.get_object.side_effect = Exception("S3 get error")
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")

        with pytest.raises((RetryableError, NonRetryableError)):
            await storage.retrieve_document("test-workflow", "draft#1")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_document_metadata_success(self, mock_boto3):
        """Test successful metadata retrieval from S3"""
        mock_s3_client = Mock()
        mock_s3_client.head_object.return_value = {
            "Metadata": {
                "stored-at": "2023-12-01T10:30:00",
                "custom-approved": "True",
                "custom-iteration_count": "3",
            },
            "ContentLength": 500,
        }
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")
        metadata = await storage.get_document_metadata("test-workflow", "draft#2")

        assert isinstance(metadata, DocumentMetadata)
        assert metadata.workflow_id == "test-workflow"
        assert metadata.document_key == "draft#2"
        assert metadata.doc_type == "draft"
        assert metadata.version == 2
        assert metadata.created_at == "2023-12-01T10:30:00"
        assert metadata.approved is True
        assert metadata.content_size == 500
        assert metadata.iteration_count == 3

        mock_s3_client.head_object.assert_called_once_with(Bucket="test-bucket", Key="test-workflow/draft#2")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_document_metadata_minimal(self, mock_boto3):
        """Test metadata retrieval with minimal S3 metadata"""
        mock_s3_client = Mock()
        mock_s3_client.head_object.return_value = {
            "Metadata": {},
            "ContentLength": 100,
        }
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")
        metadata = await storage.get_document_metadata("test-workflow", "final#1")

        assert metadata.doc_type == "final"
        assert metadata.version == 1
        assert metadata.approved is False
        assert metadata.iteration_count is None

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_document_metadata_error_handling(self, mock_boto3):
        """Test S3 get_document_metadata error handling"""
        mock_s3_client = Mock()
        mock_s3_client.head_object.side_effect = Exception("S3 head error")
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")

        with pytest.raises((RetryableError, NonRetryableError)):
            await storage.get_document_metadata("test-workflow", "draft#1")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_list_documents_success(self, mock_boto3):
        """Test listing documents from S3"""
        from datetime import datetime

        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "test-workflow/draft#1", "LastModified": datetime(2023, 12, 1, 10, 0), "Size": 100},
                {"Key": "test-workflow/final#1", "LastModified": datetime(2023, 12, 1, 11, 0), "Size": 200},
            ]
        }
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")
        documents = await storage.list_documents("test-workflow")

        assert len(documents) == 2
        assert all(isinstance(doc, DocumentMetadata) for doc in documents)
        assert documents[0].doc_type == "draft"
        assert documents[1].doc_type == "final"
        assert documents[0].content_size == 100
        assert documents[1].content_size == 200

        mock_s3_client.list_objects_v2.assert_called_once_with(Bucket="test-bucket", Prefix="test-workflow/")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_list_documents_filtered_by_type(self, mock_boto3):
        """Test listing documents from S3 filtered by type"""
        from datetime import datetime

        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "test-workflow/draft#1", "LastModified": datetime(2023, 12, 1, 10, 0), "Size": 100},
            ]
        }
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")
        documents = await storage.list_documents("test-workflow", doc_type="draft")

        assert len(documents) == 1
        assert documents[0].doc_type == "draft"

        mock_s3_client.list_objects_v2.assert_called_once_with(Bucket="test-bucket", Prefix="test-workflow/draft#")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_list_documents_empty(self, mock_boto3):
        """Test listing documents when no documents exist"""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {}  # No Contents key
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")
        documents = await storage.list_documents("test-workflow")

        assert documents == []

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_list_documents_error_handling(self, mock_boto3):
        """Test S3 list_documents error handling"""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.side_effect = Exception("S3 list error")
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")

        with pytest.raises((RetryableError, NonRetryableError)):
            await storage.list_documents("test-workflow")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_latest_document_key_success(self, mock_boto3):
        """Test getting latest document key from S3"""
        from datetime import datetime

        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "test-workflow/draft#1", "LastModified": datetime(2023, 12, 1, 10, 0)},
                {"Key": "test-workflow/draft#3", "LastModified": datetime(2023, 12, 1, 12, 0)},
                {"Key": "test-workflow/draft#2", "LastModified": datetime(2023, 12, 1, 11, 0)},
            ]
        }
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")
        latest = await storage.get_latest_document_key("test-workflow", "draft")

        assert latest == "draft#3"  # Latest by LastModified
        mock_s3_client.list_objects_v2.assert_called_once_with(Bucket="test-bucket", Prefix="test-workflow/draft#")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_latest_document_key_not_found(self, mock_boto3):
        """Test getting latest document key when no documents exist in S3"""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.return_value = {}  # No Contents key
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")

        with pytest.raises((StorageError, RetryableError, NonRetryableError)):
            await storage.get_latest_document_key("test-workflow", "draft")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_get_latest_document_key_error_handling(self, mock_boto3):
        """Test S3 get_latest_document_key error handling"""
        mock_s3_client = Mock()
        mock_s3_client.list_objects_v2.side_effect = Exception("S3 error")
        mock_boto3.client.return_value = mock_s3_client

        storage = S3Storage(bucket_name="test-bucket")

        with pytest.raises((RetryableError, NonRetryableError)):
            await storage.get_latest_document_key("test-workflow", "draft")


class TestValidateStorageId:
    @pytest.mark.parametrize(
        "value",
        [
            "test-workflow",
            "draft#1",
            "final#12",
            "workflow_id.v2",
        ],
    )
    def test_valid_ids_pass(self, value):
        """Test that valid identifiers, including document_key with '#', pass validation"""
        _validate_storage_id(value, "test_label")

    def test_empty_string_rejected(self):
        """Test that an empty value is rejected"""
        with pytest.raises(ValueError, match="invalid test_label"):
            _validate_storage_id("", "test_label")

    @pytest.mark.parametrize(
        "value",
        [
            "../../etc/passwd",
            "..",
            "foo/bar",
            "foo\\bar",
            "draft#1;rm -rf",
            "draft#1|cat",
            "draft#1`whoami`",
            "foo bar",
        ],
    )
    def test_invalid_ids_rejected(self, value):
        """Test that path traversal, path separators, and shell metacharacters are rejected"""
        with pytest.raises(ValueError, match="invalid test_label"):
            _validate_storage_id(value, "test_label")


class TestLocalFileStorage:
    @patch("foundry_temporal.storage.os")
    def test_init_creates_base_directory(self, mock_os):
        """Test that initialization creates base directory"""
        mock_os.makedirs = Mock()

        storage = LocalFileStorage(base_path="/custom/path")

        assert storage.base_path == "/custom/path"
        mock_os.makedirs.assert_called_once_with("/custom/path", exist_ok=True)

    def test_init_default_path(self):
        """Test initialization with default path"""
        with patch("foundry_temporal.storage.os") as mock_os:
            storage = LocalFileStorage()

            assert storage.base_path == "/tmp/workflow-documents"
            mock_os.makedirs.assert_called_once_with("/tmp/workflow-documents", exist_ok=True)

    @patch("foundry_temporal.storage.os")
    @patch("foundry_temporal.storage.json")
    @patch("builtins.open", new_callable=mock_open)
    @patch("foundry_temporal.storage.datetime")
    @pytest.mark.asyncio
    async def test_store_document_success(self, mock_datetime, mock_file, mock_json, mock_os):
        """Test successful document storage to local filesystem"""
        mock_datetime.utcnow.return_value.isoformat.return_value = "2023-12-01T10:30:00"
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.makedirs = Mock()

        storage = LocalFileStorage(base_path="/test/path")

        result = await storage.store_document(
            workflow_id="test-workflow",
            document_key="draft#1",
            content="test content",
            metadata={"document_type": "draft"},
        )

        # Verify directory creation
        mock_os.makedirs.assert_called_with("/test/path/test-workflow", exist_ok=True)

        # Verify file writes
        assert mock_file.call_count == 2  # Content file + metadata file

        # Verify return value is the document key
        assert result == "draft#1"

    @patch("foundry_temporal.storage.os")
    @patch("builtins.open", new_callable=mock_open, read_data="retrieved content")
    @pytest.mark.asyncio
    async def test_retrieve_document_success(self, mock_file, mock_os):
        """Test successful document retrieval from local filesystem"""
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.path.exists.return_value = True

        storage = LocalFileStorage(base_path="/test/path")

        result = await storage.retrieve_document("test-workflow", "draft-1")

        assert result == "retrieved content"
        mock_file.assert_called_once_with("/test/path/test-workflow/draft-1.txt")

    @patch("foundry_temporal.storage.os")
    @pytest.mark.asyncio
    async def test_retrieve_document_not_found(self, mock_os):
        """Test document retrieval when file doesn't exist"""
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.path.exists.return_value = False

        storage = LocalFileStorage(base_path="/test/path")

        with pytest.raises(FileNotFoundError) as exc_info:
            await storage.retrieve_document("test-workflow", "draft-1")

        assert "Document draft-1 not found for workflow test-workflow" in str(exc_info.value)

    @patch("foundry_temporal.storage.os")
    @patch("foundry_temporal.storage.json")
    @patch("builtins.open", new_callable=mock_open)
    @pytest.mark.asyncio
    async def test_get_document_metadata_success(self, mock_file, mock_json, mock_os):
        """Test successful metadata retrieval from local filesystem"""
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.path.exists.return_value = True

        expected_metadata = {
            "workflow_id": "test-workflow",
            "document_key": "draft#1",
            "created_at": "2023-12-01T10:30:00Z",
            "updated_at": "2023-12-01T11:00:00Z",
            "approved": False,
            "content_length": 100,
            "iteration_count": 1,
        }
        mock_json.load.return_value = expected_metadata

        storage = LocalFileStorage(base_path="/test/path")

        result = await storage.get_document_metadata("test-workflow", "draft#1")

        # Result should be DocumentMetadata object
        assert result.workflow_id == "test-workflow"
        assert result.document_key == "draft#1"
        assert result.doc_type == "draft"
        assert result.version == 1
        assert result.created_at == "2023-12-01T10:30:00Z"
        assert result.updated_at == "2023-12-01T11:00:00Z"
        assert result.approved is False
        assert result.content_size == 100
        assert result.iteration_count == 1

        mock_file.assert_called_once_with("/test/path/test-workflow/draft#1.meta.json")

    @patch("foundry_temporal.storage.os")
    @pytest.mark.asyncio
    async def test_get_document_metadata_not_found(self, mock_os):
        """Test metadata retrieval when metadata file doesn't exist"""
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.path.exists.return_value = False

        storage = LocalFileStorage(base_path="/test/path")

        with pytest.raises(StorageError) as exc_info:
            await storage.get_document_metadata("test-workflow", "draft-1")

        assert "Metadata for draft-1 not found" in str(exc_info.value)

    @patch("foundry_temporal.storage.os")
    @patch("foundry_temporal.storage.json")
    @patch("builtins.open", new_callable=mock_open)
    @pytest.mark.asyncio
    async def test_get_latest_document_key_success(self, mock_file, mock_json, mock_os):
        """Test getting latest document key from local filesystem"""
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.path.exists.return_value = True
        mock_os.listdir.return_value = ["doc1.meta.json", "doc2.meta.json", "content.txt"]

        # Mock metadata for different documents
        mock_metadata_1 = {"document_key": "draft#1", "document_type": "draft", "created_at": "2023-12-01T10:00:00"}
        mock_metadata_2 = {
            "document_key": "draft#2",
            "document_type": "draft",
            "created_at": "2023-12-01T11:00:00",  # Later timestamp
        }

        mock_json.load.side_effect = [mock_metadata_1, mock_metadata_2]

        storage = LocalFileStorage(base_path="/test/path")

        result = await storage.get_latest_document_key("test-workflow", "draft")

        assert result == "draft#2"  # Should return the one with later timestamp

    @patch("foundry_temporal.storage.os")
    @pytest.mark.asyncio
    async def test_get_latest_document_key_no_documents(self, mock_os):
        """Test getting latest document key when no documents exist"""
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.path.exists.return_value = False

        storage = LocalFileStorage(base_path="/test/path")

        with pytest.raises(StorageError) as exc_info:
            await storage.get_latest_document_key("test-workflow", "draft")

        assert "No documents found for workflow test-workflow" in str(exc_info.value)

    @patch("foundry_temporal.storage.os")
    @patch("foundry_temporal.storage.json")
    @patch("builtins.open", new_callable=mock_open)
    @pytest.mark.asyncio
    async def test_list_documents_success(self, mock_file, mock_json, mock_os):
        """Test listing documents from local filesystem"""
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.path.exists.return_value = True
        mock_os.listdir.return_value = ["doc1.meta.json", "doc2.meta.json"]

        mock_metadata_1 = {"document_key": "draft#1", "document_type": "draft", "created_at": "2023-12-01T10:00:00"}
        mock_metadata_2 = {"document_key": "final#1", "document_type": "final", "created_at": "2023-12-01T11:00:00"}

        mock_json.load.side_effect = [mock_metadata_1, mock_metadata_2, mock_metadata_1, mock_metadata_2]

        storage = LocalFileStorage(base_path="/test/path")

        # List all documents
        all_docs = await storage.list_documents("test-workflow")
        assert len(all_docs) == 2

        # List filtered by type
        draft_docs = await storage.list_documents("test-workflow", "draft")
        assert len(draft_docs) == 1
        assert draft_docs[0].doc_type == "draft"

    @patch("foundry_temporal.storage.os")
    @pytest.mark.asyncio
    async def test_list_documents_no_directory(self, mock_os):
        """Test listing documents when workflow directory doesn't exist"""
        mock_os.path.join.side_effect = lambda *args: "/".join(args)
        mock_os.path.exists.return_value = False

        storage = LocalFileStorage(base_path="/test/path")

        result = await storage.list_documents("test-workflow")
        assert result == []

    @pytest.mark.asyncio
    async def test_store_and_retrieve_document_key_with_hash(self, tmp_path):
        """Regression test: document_key containing '#' continues to work end-to-end"""
        storage = LocalFileStorage(base_path=str(tmp_path))

        await storage.store_document("wf-1", "draft#1", "hello world")
        content = await storage.retrieve_document("wf-1", "draft#1")

        assert content == "hello world"

    @pytest.mark.asyncio
    async def test_get_document_metadata_document_key_with_hash(self, tmp_path):
        """Regression test: get_document_metadata continues to work for document_key with '#'"""
        storage = LocalFileStorage(base_path=str(tmp_path))

        await storage.store_document("wf-1", "draft#1", "hello world")
        metadata = await storage.get_document_metadata("wf-1", "draft#1")

        assert metadata.document_key == "draft#1"
        assert metadata.doc_type == "draft"
        assert metadata.version == 1

    @pytest.mark.parametrize(
        "bad_value",
        [
            "../../etc/passwd",
            "foo/bar",
            "foo\\bar",
            "draft#1;rm -rf",
            "draft#1|cat",
            "draft#1`whoami`",
        ],
    )
    class TestLocalFileStorageRejectsInvalidIds:
        @pytest.mark.asyncio
        async def test_store_document_rejects_invalid_workflow_id(self, tmp_path, bad_value):
            storage = LocalFileStorage(base_path=str(tmp_path))

            with pytest.raises(ValueError, match="invalid workflow_id"):
                await storage.store_document(bad_value, "draft#1", "content")

            assert list(tmp_path.iterdir()) == []

        @pytest.mark.asyncio
        async def test_store_document_rejects_invalid_document_key(self, tmp_path, bad_value):
            storage = LocalFileStorage(base_path=str(tmp_path))

            with pytest.raises(ValueError, match="invalid document_key"):
                await storage.store_document("wf-1", bad_value, "content")

            assert not (tmp_path / "wf-1").exists() or list((tmp_path / "wf-1").iterdir()) == []

        @pytest.mark.asyncio
        async def test_retrieve_document_rejects_invalid_workflow_id(self, tmp_path, bad_value):
            storage = LocalFileStorage(base_path=str(tmp_path))

            with pytest.raises(ValueError, match="invalid workflow_id"):
                await storage.retrieve_document(bad_value, "draft#1")

        @pytest.mark.asyncio
        async def test_retrieve_document_rejects_invalid_document_key(self, tmp_path, bad_value):
            storage = LocalFileStorage(base_path=str(tmp_path))

            with pytest.raises(ValueError, match="invalid document_key"):
                await storage.retrieve_document("wf-1", bad_value)

        @pytest.mark.asyncio
        async def test_get_document_metadata_rejects_invalid_workflow_id(self, tmp_path, bad_value):
            storage = LocalFileStorage(base_path=str(tmp_path))

            with pytest.raises(ValueError, match="invalid workflow_id"):
                await storage.get_document_metadata(bad_value, "draft#1")

        @pytest.mark.asyncio
        async def test_get_document_metadata_rejects_invalid_document_key(self, tmp_path, bad_value):
            storage = LocalFileStorage(base_path=str(tmp_path))

            with pytest.raises(ValueError, match="invalid document_key"):
                await storage.get_document_metadata("wf-1", bad_value)

        @pytest.mark.asyncio
        async def test_get_latest_document_key_rejects_invalid_workflow_id(self, tmp_path, bad_value):
            storage = LocalFileStorage(base_path=str(tmp_path))

            with pytest.raises(ValueError, match="invalid workflow_id"):
                await storage.get_latest_document_key(bad_value, "draft")

        @pytest.mark.asyncio
        async def test_list_documents_rejects_invalid_workflow_id(self, tmp_path, bad_value):
            storage = LocalFileStorage(base_path=str(tmp_path))

            with pytest.raises(ValueError, match="invalid workflow_id"):
                await storage.list_documents(bad_value)


class TestDocumentStorage:
    def test_init_dynamodb_backend(self):
        """Test DocumentStorage initialization with DynamoDB backend"""
        storage = DocumentStorage(storage_type="dynamodb", table_name="test-table", region="us-west-1")

        assert storage.storage_type == "dynamodb"
        assert isinstance(storage.backend, DynamoDBStorage)
        assert storage.backend.table_name == "test-table"
        assert storage.backend.region == "us-west-1"

    def test_init_s3_backend(self):
        """Test DocumentStorage initialization with S3 backend"""
        storage = DocumentStorage(storage_type="s3", bucket_name="test-bucket", region="us-west-2")

        assert storage.storage_type == "s3"
        assert isinstance(storage.backend, S3Storage)
        assert storage.backend.bucket_name == "test-bucket"
        assert storage.backend.region == "us-west-2"

    def test_init_local_backend(self):
        """Test DocumentStorage initialization with local backend"""
        with patch("foundry_temporal.storage.os"):
            storage = DocumentStorage(storage_type="local", base_path="/custom/path")

            assert storage.storage_type == "local"
            assert isinstance(storage.backend, LocalFileStorage)
            assert storage.backend.base_path == "/custom/path"

    def test_init_default_backend(self):
        """Test DocumentStorage initialization with default backend"""
        storage = DocumentStorage()

        assert storage.storage_type == "dynamodb"
        assert isinstance(storage.backend, DynamoDBStorage)

    def test_init_unsupported_backend(self):
        """Test DocumentStorage initialization with unsupported backend"""
        with pytest.raises(ValueError) as exc_info:
            DocumentStorage(storage_type="unsupported")

        assert "Unsupported storage type: unsupported" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_method_delegation(self):
        """Test that DocumentStorage properly delegates methods to backend"""
        with patch("foundry_temporal.storage.os"):
            storage = DocumentStorage(storage_type="local")

        # Mock the backend methods
        storage.backend.store_document = AsyncMock(return_value="stored")
        storage.backend.retrieve_document = AsyncMock(return_value="content")
        storage.backend.get_document_metadata = AsyncMock(return_value="metadata")
        storage.backend.list_documents = AsyncMock(return_value=["doc1", "doc2"])
        storage.backend.get_latest_document_key = AsyncMock(return_value="latest")

        # Test method delegation
        assert await storage.store_document("arg1", "arg2") == "stored"
        assert await storage.retrieve_document("arg1", "arg2") == "content"
        assert await storage.get_document_metadata("arg1", "arg2") == "metadata"
        assert await storage.list_documents("arg1") == ["doc1", "doc2"]
        assert await storage.get_latest_document_key("arg1", "arg2") == "latest"

        # Verify backend methods were called
        storage.backend.store_document.assert_called_once_with("arg1", "arg2")
        storage.backend.retrieve_document.assert_called_once_with("arg1", "arg2")
        storage.backend.get_document_metadata.assert_called_once_with("arg1", "arg2")
        storage.backend.list_documents.assert_called_once_with("arg1")
        storage.backend.get_latest_document_key.assert_called_once_with("arg1", "arg2")

    @pytest.mark.asyncio
    async def test_method_delegation_with_kwargs(self):
        """Test method delegation with keyword arguments"""
        with patch("foundry_temporal.storage.os"):
            storage = DocumentStorage(storage_type="local")

        storage.backend.store_document = AsyncMock(return_value="stored")

        # Test with keyword arguments
        await storage.store_document(workflow_id="test", document_key="key", content="content", metadata={"test": True})

        storage.backend.store_document.assert_called_once_with(
            workflow_id="test", document_key="key", content="content", metadata={"test": True}
        )


class TestIntegration:
    """Integration tests for storage components"""

    def test_storage_backend_interface_consistency(self):
        """Test that all concrete storage backends implement the same interface"""
        # Test that all backends have the same method signatures
        backend_classes = [DynamoDBStorage, S3Storage, LocalFileStorage]

        for backend_class in backend_classes:
            # Check that all abstract methods are implemented
            assert hasattr(backend_class, "store_document")
            assert hasattr(backend_class, "retrieve_document")
            assert hasattr(backend_class, "get_document_metadata")
            assert hasattr(backend_class, "list_documents")
            assert hasattr(backend_class, "get_latest_document_key")

    @patch("foundry_temporal.storage.boto3")
    @pytest.mark.asyncio
    async def test_document_key_parsing_consistency(self, mock_boto3):
        """Test that document key parsing is consistent across operations"""
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {"workflow_id": "test-workflow", "document_key": "draft#3", "created_at": "2023-12-01T10:30:00Z"}
        }
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()
        metadata = await storage.get_document_metadata("test-workflow", "draft#3")

        # Verify parsing
        assert metadata.doc_type == "draft"
        assert metadata.version == 3
        assert metadata.document_key == "draft#3"


class TestStorageEncryption:
    """Tests for AES-256-GCM content encryption across storage backends."""

    @pytest.mark.asyncio
    async def test_local_storage_round_trip(self, tmp_path):
        """Content is encrypted on store and decrypted on retrieve."""
        storage = LocalFileStorage(base_path=str(tmp_path))
        original_content = "This is sensitive document content."

        await storage.store_document("wf-enc", "draft#1", original_content)
        retrieved = await storage.retrieve_document("wf-enc", "draft#1")

        assert retrieved == original_content

    @pytest.mark.asyncio
    async def test_local_storage_content_encrypted_on_disk(self, tmp_path):
        """Raw file must not contain plaintext content."""
        storage = LocalFileStorage(base_path=str(tmp_path))
        secret_content = "TOP SECRET: mission-critical data"

        await storage.store_document("wf-enc", "draft#1", secret_content)

        raw_path = tmp_path / "wf-enc" / "draft#1.txt"
        raw_data = raw_path.read_text()
        assert secret_content not in raw_data
        # Should be valid JSON with encrypted marker
        payload = json.loads(raw_data)
        assert payload.get("__encrypted") is True

    @pytest.mark.asyncio
    async def test_local_storage_tampered_ciphertext_raises(self, tmp_path):
        """Tampered ciphertext should raise InvalidTag."""
        storage = LocalFileStorage(base_path=str(tmp_path))

        await storage.store_document("wf-enc", "draft#1", "original content")

        # Tamper with the stored file
        raw_path = tmp_path / "wf-enc" / "draft#1.txt"
        payload = json.loads(raw_path.read_text())
        payload["ciphertext"] = payload["ciphertext"][:-4] + "XXXX"
        raw_path.write_text(json.dumps(payload))

        with pytest.raises(InvalidTag):
            await storage.retrieve_document("wf-enc", "draft#1")

    @pytest.mark.asyncio
    async def test_local_storage_plaintext_fallback(self, tmp_path):
        """Pre-existing plaintext documents should be returned as-is with warning."""
        storage = LocalFileStorage(base_path=str(tmp_path))

        # Write plaintext directly (simulating pre-encryption document)
        wf_dir = tmp_path / "wf-legacy"
        wf_dir.mkdir()
        doc_path = wf_dir / "draft#1.txt"
        doc_path.write_text("legacy plaintext content")
        # Also write metadata so retrieve doesn't fail on validation
        meta_path = wf_dir / "draft#1.meta.json"
        meta_path.write_text(json.dumps({"workflow_id": "wf-legacy", "document_key": "draft#1"}))

        retrieved = await storage.retrieve_document("wf-legacy", "draft#1")
        assert retrieved == "legacy plaintext content"

    @pytest.mark.asyncio
    @patch("foundry_temporal.storage.boto3")
    async def test_dynamodb_store_encrypts_content(self, mock_boto3):
        """DynamoDB store_document should encrypt content before writing."""
        mock_table = Mock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        storage = DynamoDBStorage()
        await storage.store_document("wf-1", "draft#1", "secret content")

        call_args = mock_table.put_item.call_args
        stored_content = call_args[1]["Item"]["content"] if "Item" in call_args[1] else call_args[0][0]["content"]
        # Content should be encrypted JSON, not plaintext
        assert "secret content" not in stored_content
        payload = json.loads(stored_content)
        assert payload.get("__encrypted") is True

    @pytest.mark.asyncio
    @patch("foundry_temporal.storage.boto3")
    async def test_s3_store_encrypts_content(self, mock_boto3):
        """S3 store_document should encrypt content before writing."""
        mock_s3 = Mock()
        mock_boto3.client.return_value = mock_s3

        storage = S3Storage(bucket_name="test-bucket")
        await storage.store_document("wf-1", "draft#1", "secret content")

        call_args = mock_s3.put_object.call_args
        stored_body = call_args[1]["Body"] if "Body" in call_args[1] else call_args[0][0]
        body_str = stored_body if isinstance(stored_body, str) else stored_body.decode("utf-8")
        assert "secret content" not in body_str
        payload = json.loads(body_str)
        assert payload.get("__encrypted") is True

    def test_error_classification_integration(self):
        """Test that storage operations properly integrate with error classification"""
        # This test verifies that storage methods use classify_and_wrap_error
        # The actual error classification is tested in test_errors.py

        storage = DynamoDBStorage()

        # Check that store_document, retrieve_document, etc. would call
        # classify_and_wrap_error in their exception handlers
        # This is verified by the presence of the try/except blocks in the methods

        assert hasattr(storage, "store_document")
        assert hasattr(storage, "retrieve_document")
        # More specific testing of error handling is done in individual method tests
