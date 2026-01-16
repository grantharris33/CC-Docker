"""Session management endpoints."""

import logging
from typing import Optional

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_redis
from app.core.security import User, get_current_user
from app.models.session import (
    SessionCreate,
    SessionDetail,
    SessionList,
    SessionResponse,
    SessionStatus,
)
from app.services.container import ContainerManager, get_container_manager
from app.services.session import SessionService

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_session_service(
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
    container_manager: ContainerManager = Depends(get_container_manager),
) -> SessionService:
    """Dependency for session service."""
    return SessionService(db, redis_client, container_manager)


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: SessionCreate,
    user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
):
    """
    Create a new Claude Code session.

    Creates a new Docker container with Claude Code and returns
    session details including the WebSocket URL for streaming.
    """
    try:
        return await session_service.create_session(request, user.user_id)
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
):
    """
    Get session details.

    Returns detailed information about a session including
    status, container info, and usage statistics.
    """
    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )
    return session


@router.get("", response_model=SessionList)
async def list_sessions(
    session_status: Optional[SessionStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
):
    """
    List all sessions.

    Returns a paginated list of sessions with optional status filtering.
    """
    sessions, total = await session_service.list_sessions(
        user.user_id, session_status, limit, offset
    )
    return SessionList(
        sessions=sessions,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{session_id}/stop", response_model=SessionDetail)
async def stop_session(
    session_id: str,
    user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
):
    """
    Stop a running session.

    Gracefully stops the Claude Code container and marks the session as stopped.
    """
    try:
        return await session_service.stop_session(session_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to stop session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
):
    """
    Delete a session.

    Stops the container, removes all resources, and deletes the session record.
    """
    try:
        await session_service.delete_session(session_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to delete session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
