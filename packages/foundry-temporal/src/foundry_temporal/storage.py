# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Storage Abstraction for Workflow-Managed Persistence

Note from architecture: This abstraction is for workflows where workers manage
document persistence. For workflows using agent-managed persistence (e.g.,
research workflow where agent persists to DynamoDB via MCP tools), workers
only query for metadata using standard AWS SDK rather than this abstraction.
"""

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal, cast

# Optional imports for cloud services (may not be available in all environments)
try:
    import boto3  # type: ignore
    from boto3.dynamodb.conditions import Key  # type: ignore
except ImportError:
    boto3 = None  # type: ignore
    Key = None  # type: ignore

from foundry_agent_core.encryption import decrypt, encrypt, is_encrypted, load_encryption_key

from .errors import StorageError, classify_and_wrap_error
from .models import DocumentMetadata

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.#-]+$")


def _validate_storage_id(value: str, label: str) -> None:
    """Reject path traversal, path separators, and disallowed characters in a storage identifier."""
    if not value or ".." in value or "/" in value or "\\" in value or not _SAFE_ID.fullmatch(value):
        raise ValueError(f"invalid {label}: {value!r}")


class StorageBackend(ABC):
    """Abstract base class for storage backends"""

    def __init__(self) -> None:
        self._encryption_key = load_encryption_key(env_var="FOUNDRY_TEMPORAL_ENCRYPTION_KEY")

    def _encrypt_content(self, content: str) -> str:
        """Encrypt content string for storage."""
        payload = encrypt({"content": content}, self._encryption_key)
        return json.dumps(payload)

    def _decrypt_content(self, stored: str) -> str:
        """Decrypt stored content, with graceful plaintext fallback."""
        try:
            payload = json.loads(stored)
        except Exception:
            logger.warning("Document contains non-JSON data, returning as plaintext")
            return stored

        if not isinstance(payload, dict) or not is_encrypted(payload):
            logger.warning("Document is not encrypted, returning as plaintext")
            return stored

        decrypted = decrypt(payload, self._encryption_key)
        return decrypted["content"]

    @abstractmethod
    async def store_document(
        self, workflow_id: str, document_key: str, content: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """Store document and return storage key"""
        pass

    @abstractmethod
    async def retrieve_document(self, workflow_id: str, document_key: str) -> str:
        """Retrieve document content"""
        pass

    @abstractmethod
    async def get_document_metadata(self, workflow_id: str, document_key: str) -> DocumentMetadata:
        """Get document metadata"""
        pass

    @abstractmethod
    async def list_documents(self, workflow_id: str, doc_type: str | None = None) -> list[DocumentMetadata]:
        """List documents for workflow"""
        pass

    @abstractmethod
    async def get_latest_document_key(self, workflow_id: str, doc_type: str) -> str:
        """Get latest document key for type"""
        pass


class DynamoDBStorage(StorageBackend):
    """
    DynamoDB storage backend

    Table structure from architecture:
    - Partition Key: workflow_id (String)
    - Sort Key: document_key (String) - Format: {type}#{version}
    - Attributes: content, metadata, created_at, updated_at
    """

    def __init__(self, table_name: str = "research-documents", region: str = "us-east-1"):
        super().__init__()
        self.table_name = table_name
        self.region = region
        self._table = None

    @property
    def table(self):  # type: ignore
        """Lazy-loaded DynamoDB table resource"""
        if self._table is None:
            dynamodb = boto3.resource("dynamodb", region_name=self.region)  # type: ignore
            self._table = dynamodb.Table(self.table_name)  # type: ignore
        return self._table

    async def store_document(
        self, workflow_id: str, document_key: str, content: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """Store document to DynamoDB"""
        try:
            timestamp = datetime.utcnow().isoformat()
            encrypted_content = self._encrypt_content(content)

            item = {
                "workflow_id": workflow_id,
                "document_key": document_key,
                "content": encrypted_content,
                "created_at": timestamp,
                "updated_at": timestamp,
                "content_size": len(content),
            }

            # Add metadata if provided
            if metadata:
                item["metadata"] = metadata

            self.table.put_item(Item=item)
            return document_key

        except Exception as e:
            raise classify_and_wrap_error(e, f"store_document: {workflow_id}/{document_key}") from e

    async def retrieve_document(self, workflow_id: str, document_key: str) -> str:
        """Retrieve document content from DynamoDB"""
        try:
            response = self.table.get_item(Key={"workflow_id": workflow_id, "document_key": document_key})

            if "Item" not in response:
                raise StorageError(f"Document not found: {workflow_id}/{document_key}")

            stored = response["Item"].get("content", "")
            return self._decrypt_content(stored)

        except StorageError:
            raise  # Re-raise StorageError as-is
        except Exception as e:
            raise classify_and_wrap_error(e, f"retrieve_document: {workflow_id}/{document_key}") from e

    async def get_document_metadata(self, workflow_id: str, document_key: str) -> DocumentMetadata:
        """Get document metadata from DynamoDB"""
        try:
            response = self.table.get_item(Key={"workflow_id": workflow_id, "document_key": document_key})

            if "Item" not in response:
                raise StorageError(f"Document not found: {workflow_id}/{document_key}")

            item = response["Item"]

            # Parse document type and version from key
            doc_type, version_str = document_key.split("#", 1)
            version = int(version_str) if version_str.isdigit() else 1

            return DocumentMetadata(
                workflow_id=workflow_id,
                document_key=document_key,
                version=version,
                doc_type=cast(Literal["draft", "final"], doc_type),
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
                approved=item.get("approved", False),
                content_size=item.get("content_size"),
                iteration_count=item.get("iteration_count"),
            )

        except StorageError:
            raise  # Re-raise StorageError as-is
        except Exception as e:
            raise classify_and_wrap_error(e, f"get_document_metadata: {workflow_id}/{document_key}") from e

    async def list_documents(self, workflow_id: str, doc_type: str | None = None) -> list[DocumentMetadata]:
        """List documents for workflow"""
        try:
            if doc_type:
                # Query specific document type
                response = self.table.query(
                    KeyConditionExpression=(
                        Key("workflow_id").eq(workflow_id) & Key("document_key").begins_with(f"{doc_type}#")  # type: ignore
                    )
                )
            else:
                # Query all documents for workflow
                response = self.table.query(KeyConditionExpression=Key("workflow_id").eq(workflow_id))  # type: ignore

            documents = []
            for item in response["Items"]:
                doc_key = item["document_key"]
                doc_type_parsed, version_str = doc_key.split("#", 1)
                version = int(version_str) if version_str.isdigit() else 1

                documents.append(
                    DocumentMetadata(
                        workflow_id=workflow_id,
                        document_key=doc_key,
                        version=version,
                        doc_type=cast(Literal["draft", "final"], doc_type_parsed),
                        created_at=item.get("created_at", ""),
                        updated_at=item.get("updated_at", ""),
                        approved=item.get("approved", False),
                        content_size=item.get("content_size"),
                        iteration_count=item.get("iteration_count"),
                    )
                )

            return documents

        except StorageError:
            raise  # Re-raise StorageError as-is
        except Exception as e:
            raise classify_and_wrap_error(e, f"list_documents: {workflow_id}") from e

    async def get_latest_document_key(self, workflow_id: str, doc_type: str) -> str:
        """Get latest document key for type (from architecture specification)"""
        try:
            response = self.table.query(
                KeyConditionExpression=(
                    Key("workflow_id").eq(workflow_id) & Key("document_key").begins_with(f"{doc_type}#")  # type: ignore
                ),
                ScanIndexForward=False,  # Reverse order to get latest first
                Limit=1,
            )

            if not response["Items"]:
                raise StorageError(f"No documents found for {workflow_id}/{doc_type}")

            return response["Items"][0]["document_key"]

        except StorageError:
            raise  # Re-raise StorageError as-is
        except Exception as e:
            raise classify_and_wrap_error(e, f"get_latest_document_key: {workflow_id}/{doc_type}") from e


class S3Storage(StorageBackend):
    """S3 storage backend for document storage"""

    def __init__(self, bucket_name: str, region: str = "us-east-1"):
        super().__init__()
        self.bucket_name = bucket_name
        self.region = region
        self._s3 = None

    @property
    def s3(self):  # type: ignore
        """Lazy-loaded S3 client"""
        if self._s3 is None:
            self._s3 = boto3.client("s3", region_name=self.region)  # type: ignore
        return self._s3

    async def store_document(
        self, workflow_id: str, document_key: str, content: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """Store document to S3"""
        try:
            s3_key = f"{workflow_id}/{document_key}"

            # Prepare metadata for S3
            s3_metadata = {
                "workflow-id": workflow_id,
                "document-key": document_key,
                "stored-at": datetime.utcnow().isoformat(),
            }

            if metadata:
                # S3 metadata keys must be strings
                for k, v in metadata.items():
                    s3_metadata[f"custom-{k}"] = str(v)

            encrypted_content = self._encrypt_content(content)
            self.s3.put_object(
                Bucket=self.bucket_name, Key=s3_key, Body=encrypted_content.encode("utf-8"), Metadata=s3_metadata
            )

            return s3_key

        except Exception as e:
            raise classify_and_wrap_error(
                e, f"store_document: s3://{self.bucket_name}/{workflow_id}/{document_key}"
            ) from e

    async def retrieve_document(self, workflow_id: str, document_key: str) -> str:
        """Retrieve document content from S3"""
        try:
            s3_key = f"{workflow_id}/{document_key}"
            response = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            stored = response["Body"].read().decode("utf-8")
            return self._decrypt_content(stored)
        except Exception as e:
            raise classify_and_wrap_error(
                e, f"retrieve_document: s3://{self.bucket_name}/{workflow_id}/{document_key}"
            ) from e

    async def get_document_metadata(self, workflow_id: str, document_key: str) -> DocumentMetadata:
        """Get document metadata from S3"""
        try:
            s3_key = f"{workflow_id}/{document_key}"
            response = self.s3.head_object(Bucket=self.bucket_name, Key=s3_key)

            # Parse document type and version from key
            doc_type, version_str = document_key.split("#", 1)
            version = int(version_str) if version_str.isdigit() else 1

            metadata = response.get("Metadata", {})
            return DocumentMetadata(
                workflow_id=workflow_id,
                document_key=document_key,
                version=version,
                doc_type=cast(Literal["draft", "final"], doc_type),
                created_at=metadata.get("stored-at", ""),
                updated_at=metadata.get("stored-at", ""),
                approved=metadata.get("custom-approved") == "True",
                content_size=response.get("ContentLength"),
                iteration_count=(
                    int(metadata.get("custom-iteration_count", 0)) if metadata.get("custom-iteration_count") else None
                ),
            )
        except Exception as e:
            raise classify_and_wrap_error(
                e, f"get_document_metadata: s3://{self.bucket_name}/{workflow_id}/{document_key}"
            ) from e

    async def list_documents(self, workflow_id: str, doc_type: str | None = None) -> list[DocumentMetadata]:
        """List documents for workflow from S3"""
        try:
            prefix = f"{workflow_id}/"
            if doc_type:
                prefix += f"{doc_type}#"

            response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            documents = []

            for obj in response.get("Contents", []):
                key = obj["Key"]
                # Extract document_key from s3_key
                document_key = key.split("/", 1)[1]  # Remove workflow_id/ prefix

                # Parse document type and version
                doc_type_parsed, version_str = document_key.split("#", 1)
                version = int(version_str) if version_str.isdigit() else 1

                documents.append(
                    DocumentMetadata(
                        workflow_id=workflow_id,
                        document_key=document_key,
                        version=version,
                        doc_type=cast(Literal["draft", "final"], doc_type_parsed),
                        created_at=obj["LastModified"].isoformat(),
                        updated_at=obj["LastModified"].isoformat(),
                        approved=False,  # Would need to check metadata for this
                        content_size=obj["Size"],
                    )
                )

            return documents
        except Exception as e:
            raise classify_and_wrap_error(e, f"list_documents: s3://{self.bucket_name}/{workflow_id}") from e

    async def get_latest_document_key(self, workflow_id: str, doc_type: str) -> str:
        """Get latest document key for type from S3"""
        try:
            prefix = f"{workflow_id}/{doc_type}#"
            response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)

            if not response.get("Contents"):
                raise StorageError(f"No documents found for {workflow_id}/{doc_type}")

            # Sort by last modified and get the latest
            latest_obj = max(response["Contents"], key=lambda x: x["LastModified"])
            # Extract document_key from s3_key
            return latest_obj["Key"].split("/", 1)[1]  # Remove workflow_id/ prefix

        except Exception as e:
            raise classify_and_wrap_error(
                e, f"get_latest_document_key: s3://{self.bucket_name}/{workflow_id}/{doc_type}"
            ) from e


class LocalFileStorage(StorageBackend):
    """Local filesystem storage backend for development/testing"""

    def __init__(self, base_path: str = "/tmp/workflow-documents"):
        super().__init__()
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    async def store_document(
        self, workflow_id: str, document_key: str, content: str, metadata: dict[str, Any] | None = None
    ) -> str:
        _validate_storage_id(workflow_id, "workflow_id")
        _validate_storage_id(document_key, "document_key")

        # Create workflow directory
        workflow_dir = os.path.join(self.base_path, workflow_id)
        os.makedirs(workflow_dir, exist_ok=True)

        # Store document content (encrypted)
        doc_path = os.path.join(workflow_dir, f"{document_key}.txt")
        encrypted_content = self._encrypt_content(content)
        with open(doc_path, "w") as f:
            f.write(encrypted_content)

        # Store metadata
        doc_metadata = {
            "workflow_id": workflow_id,
            "document_key": document_key,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "content_length": len(content),
        }
        if metadata:
            doc_metadata.update(metadata)

        meta_path = os.path.join(workflow_dir, f"{document_key}.meta.json")
        with open(meta_path, "w") as f:
            json.dump(doc_metadata, f)

        return document_key

    async def retrieve_document(self, workflow_id: str, document_key: str) -> str:
        _validate_storage_id(workflow_id, "workflow_id")
        _validate_storage_id(document_key, "document_key")

        doc_path = os.path.join(self.base_path, workflow_id, f"{document_key}.txt")

        if not os.path.exists(doc_path):
            raise FileNotFoundError(f"Document {document_key} not found for workflow {workflow_id}")

        with open(doc_path) as f:
            stored = f.read()
        return self._decrypt_content(stored)

    async def get_document_metadata(self, workflow_id: str, document_key: str) -> DocumentMetadata:
        _validate_storage_id(workflow_id, "workflow_id")
        _validate_storage_id(document_key, "document_key")

        meta_path = os.path.join(self.base_path, workflow_id, f"{document_key}.meta.json")

        if not os.path.exists(meta_path):
            raise StorageError(f"Metadata for {document_key} not found")

        with open(meta_path) as f:
            metadata = json.load(f)

        # Parse document type and version from key
        doc_type, version_str = document_key.split("#", 1)
        version = int(version_str) if version_str.isdigit() else 1

        return DocumentMetadata(
            workflow_id=workflow_id,
            document_key=document_key,
            version=version,
            doc_type=cast(Literal["draft", "final"], doc_type),
            created_at=metadata.get("created_at", ""),
            updated_at=metadata.get("updated_at", ""),
            approved=metadata.get("approved", False),
            content_size=metadata.get("content_length"),
            iteration_count=metadata.get("iteration_count"),
        )

    async def get_latest_document_key(self, workflow_id: str, doc_type: str) -> str:
        _validate_storage_id(workflow_id, "workflow_id")

        workflow_dir = os.path.join(self.base_path, workflow_id)

        if not os.path.exists(workflow_dir):
            raise StorageError(f"No documents found for workflow {workflow_id}")

        latest_key = None
        latest_time = None

        for filename in os.listdir(workflow_dir):
            if filename.endswith(".meta.json"):
                with open(os.path.join(workflow_dir, filename)) as f:
                    metadata = json.load(f)

                document_key = metadata.get("document_key", "")
                if doc_type and not document_key.startswith(f"{doc_type}#"):
                    continue

                created_at = metadata.get("created_at")
                if not latest_time or created_at > latest_time:
                    latest_time = created_at
                    latest_key = document_key

        if not latest_key:
            raise StorageError(f"No documents found for workflow {workflow_id}")

        return latest_key

    async def list_documents(self, workflow_id: str, doc_type: str | None = None) -> list[DocumentMetadata]:
        _validate_storage_id(workflow_id, "workflow_id")

        workflow_dir = os.path.join(self.base_path, workflow_id)

        if not os.path.exists(workflow_dir):
            return []

        documents = []
        for filename in os.listdir(workflow_dir):
            if filename.endswith(".meta.json"):
                with open(os.path.join(workflow_dir, filename)) as f:
                    metadata = json.load(f)

                document_key = metadata.get("document_key", "")
                if doc_type and not document_key.startswith(f"{doc_type}#"):
                    continue

                # Parse document type and version from key
                doc_type_parsed, version_str = document_key.split("#", 1)
                version = int(version_str) if version_str.isdigit() else 1

                documents.append(
                    DocumentMetadata(
                        workflow_id=workflow_id,
                        document_key=document_key,
                        version=version,
                        doc_type=cast(Literal["draft", "final"], doc_type_parsed),
                        created_at=metadata.get("created_at", ""),
                        updated_at=metadata.get("updated_at", ""),
                        approved=metadata.get("approved", False),
                        content_size=metadata.get("content_length"),
                        iteration_count=metadata.get("iteration_count"),
                    )
                )

        return sorted(documents, key=lambda x: x.created_at)


class DocumentStorage:
    """
    Unified document storage interface

    Factory class that provides access to different storage backends
    based on configuration.
    """

    def __init__(self, storage_type: str = "dynamodb", **kwargs):
        self.storage_type = storage_type

        if storage_type == "dynamodb":
            self.backend = DynamoDBStorage(**kwargs)
        elif storage_type == "s3":
            self.backend = S3Storage(**kwargs)
        elif storage_type == "local":
            self.backend = LocalFileStorage(**kwargs)
        else:
            raise ValueError(f"Unsupported storage type: {storage_type}")

    async def store_document(self, *args, **kwargs):
        """Delegate to backend"""
        return await self.backend.store_document(*args, **kwargs)

    async def retrieve_document(self, *args, **kwargs):
        """Delegate to backend"""
        return await self.backend.retrieve_document(*args, **kwargs)

    async def get_document_metadata(self, *args, **kwargs):
        """Delegate to backend"""
        return await self.backend.get_document_metadata(*args, **kwargs)

    async def list_documents(self, *args, **kwargs):
        """Delegate to backend"""
        return await self.backend.list_documents(*args, **kwargs)

    async def get_latest_document_key(self, *args, **kwargs):
        """Delegate to backend"""
        return await self.backend.get_latest_document_key(*args, **kwargs)
