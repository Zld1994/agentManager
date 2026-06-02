"""Object-store abstractions for durable checkpoint payloads."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, cast

try:
    import boto3
except ImportError:

    class _MissingBoto3:
        def client(self, *args, **kwargs):
            raise RuntimeError("boto3 is required for S3ObjectStore")

    boto3 = _MissingBoto3()


class ObjectStore(ABC):
    """Small byte-oriented object-store interface."""

    @abstractmethod
    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Store object bytes under a key."""

    @abstractmethod
    def get_bytes(self, key: str) -> Optional[bytes]:
        """Return object bytes for a key, or None if absent."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete an object key if it exists."""


class S3ObjectStore(ObjectStore):
    """S3-compatible object store for checkpoints and artifacts."""

    def __init__(self, bucket: str, client: Any):
        if not bucket:
            raise ValueError("bucket cannot be empty")
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_settings(
        cls,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
    ) -> "S3ObjectStore":
        """Create an S3-compatible store from endpoint and credentials."""
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
        )
        return cls(bucket=bucket, client=client)

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def get_bytes(self, key: str) -> Optional[bytes]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _is_not_found_error(exc):
                return None
            raise
        return cast(bytes, response["Body"].read())

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def _is_not_found_error(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    error = response.get("Error", {}) if isinstance(response, dict) else {}
    code = error.get("Code") if isinstance(error, dict) else None
    return code in {"NoSuchKey", "404", "NotFound"}
