"""Health check endpoints."""

import logging
from typing import Dict

import redis.asyncio as redis
from aiobotocore.session import get_session
from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.dependencies import get_redis
from app.services.container import container_manager

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


async def check_redis(redis_client: redis.Redis) -> str:
    """Check Redis connectivity."""
    try:
        await redis_client.ping()
        return "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return "unhealthy"


async def check_minio() -> str:
    """Check MinIO connectivity."""
    try:
        session = get_session()
        async with session.create_client(
            "s3",
            endpoint_url=settings.minio_url,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
        ) as client:
            await client.list_buckets()
        return "healthy"
    except Exception as e:
        logger.error(f"MinIO health check failed: {e}")
        return "unhealthy"


async def check_docker() -> str:
    """Check Docker connectivity."""
    try:
        docker = await container_manager._get_docker()
        await docker.version()
        return "healthy"
    except Exception as e:
        logger.error(f"Docker health check failed: {e}")
        return "unhealthy"


@router.get("")
async def health_check(
    redis_client: redis.Redis = Depends(get_redis),
) -> Dict:
    """
    Check the health of all components.

    Returns:
        Health status of each component
    """
    redis_status = await check_redis(redis_client)
    minio_status = await check_minio()
    docker_status = await check_docker()

    components = {
        "database": "healthy",  # SQLite is always available
        "redis": redis_status,
        "minio": minio_status,
        "docker": docker_status,
    }

    overall_status = (
        "healthy"
        if all(s == "healthy" for s in components.values())
        else "unhealthy"
    )

    return {
        "status": overall_status,
        "version": settings.version,
        "components": components,
    }


@router.get("/ready")
async def readiness_check(
    redis_client: redis.Redis = Depends(get_redis),
) -> Dict:
    """
    Kubernetes readiness probe.

    Returns:
        Ready status
    """
    health = await health_check(redis_client)
    return {"ready": health["status"] == "healthy"}


@router.get("/live")
async def liveness_check() -> Dict:
    """
    Kubernetes liveness probe.

    Returns:
        Alive status
    """
    return {"alive": True}
