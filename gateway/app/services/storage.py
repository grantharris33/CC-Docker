"""MinIO storage service for workspaces and artifacts."""

import io
import json
import logging
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from aiobotocore.session import AioSession

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class StorageService:
    """Service for MinIO/S3 storage operations."""

    def __init__(self, session: AioSession):
        self._session = session
        self._client = None

    async def _get_client(self):
        """Get or create S3 client."""
        if self._client is None:
            self._client = await self._session.create_client(
                "s3",
                endpoint_url=settings.minio_url,
                aws_access_key_id=settings.minio_access_key,
                aws_secret_access_key=settings.minio_secret_key,
            ).__aenter__()
        return self._client

    async def close(self):
        """Close the S3 client."""
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def ensure_bucket(self, bucket: str = None) -> None:
        """Ensure bucket exists, create if not."""
        bucket = bucket or settings.minio_bucket
        client = await self._get_client()

        try:
            await client.head_bucket(Bucket=bucket)
        except Exception:
            await client.create_bucket(Bucket=bucket)
            logger.info(f"Created bucket: {bucket}")

    async def upload_file(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        bucket: str = None,
    ) -> str:
        """Upload a file to storage."""
        bucket = bucket or settings.minio_bucket
        client = await self._get_client()

        await client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

        logger.info(f"Uploaded file: {bucket}/{key}")
        return f"s3://{bucket}/{key}"

    async def download_file(
        self, key: str, bucket: str = None
    ) -> bytes:
        """Download a file from storage."""
        bucket = bucket or settings.minio_bucket
        client = await self._get_client()

        response = await client.get_object(Bucket=bucket, Key=key)
        async with response["Body"] as stream:
            return await stream.read()

    async def delete_file(self, key: str, bucket: str = None) -> None:
        """Delete a file from storage."""
        bucket = bucket or settings.minio_bucket
        client = await self._get_client()

        await client.delete_object(Bucket=bucket, Key=key)
        logger.info(f"Deleted file: {bucket}/{key}")

    async def list_files(
        self, prefix: str = "", bucket: str = None
    ) -> List[Dict[str, Any]]:
        """List files with a given prefix."""
        bucket = bucket or settings.minio_bucket
        client = await self._get_client()

        response = await client.list_objects_v2(Bucket=bucket, Prefix=prefix)

        files = []
        for obj in response.get("Contents", []):
            files.append(
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
            )

        return files

    async def create_workspace_snapshot(
        self, workspace_id: str, source_path: str
    ) -> str:
        """Create a snapshot of a workspace."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        key = f"workspaces/{workspace_id}/snapshot-{timestamp}.tar.gz"

        # Create tarball in memory
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for path in Path(source_path).rglob("*"):
                if path.is_file():
                    arcname = str(path.relative_to(source_path))
                    tar.add(str(path), arcname=arcname)

        buffer.seek(0)
        await self.upload_file(key, buffer.read(), "application/gzip")

        return key

    async def restore_workspace_snapshot(
        self, snapshot_key: str, target_path: str
    ) -> None:
        """Restore a workspace from a snapshot."""
        data = await self.download_file(snapshot_key)

        buffer = io.BytesIO(data)
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            tar.extractall(target_path)

        logger.info(f"Restored workspace to {target_path}")

    async def save_session_artifact(
        self,
        session_id: str,
        artifact_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Save an artifact for a session."""
        key = f"artifacts/{session_id}/{artifact_name}"
        return await self.upload_file(key, data, content_type)

    async def get_session_artifacts(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all artifacts for a session."""
        return await self.list_files(f"artifacts/{session_id}/")

    async def save_session_metadata(
        self, session_id: str, metadata: Dict[str, Any]
    ) -> str:
        """Save session metadata."""
        key = f"artifacts/{session_id}/metadata.json"
        return await self.upload_file(
            key, json.dumps(metadata).encode(), "application/json"
        )

    async def get_session_metadata(
        self, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get session metadata."""
        try:
            data = await self.download_file(f"artifacts/{session_id}/metadata.json")
            return json.loads(data)
        except Exception:
            return None


async def get_storage_service() -> StorageService:
    """Factory for StorageService."""
    from aiobotocore.session import get_session

    return StorageService(get_session())
