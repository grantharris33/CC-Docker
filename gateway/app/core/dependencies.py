"""Dependency injection providers."""

from typing import AsyncGenerator

import redis.asyncio as redis
from aiobotocore.session import get_session

from app.core.config import get_settings
from app.db.database import get_db

settings = get_settings()


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """Dependency for getting Redis connection."""
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def get_minio_client():
    """Dependency for getting MinIO client."""
    session = get_session()
    async with session.create_client(
        "s3",
        endpoint_url=settings.minio_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
    ) as client:
        yield client


from app.core.security import get_current_user

# Re-export for convenience
__all__ = ["get_db", "get_redis", "get_minio_client", "get_current_user"]
