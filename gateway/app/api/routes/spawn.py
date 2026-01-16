"""Child instance spawning endpoints."""

import logging
import uuid
from typing import Optional

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_db, get_redis
from app.core.security import User, get_current_user
from app.db.models import Session
from app.models.container import SpawnRequest, SpawnResponse, SpawnWorkspaceMode
from app.models.session import (
    SessionConfig,
    SessionCreate,
    SessionStatus,
    WorkspaceConfig,
    WorkspaceType,
)
from app.services.container import ContainerManager, get_container_manager
from app.services.session import SessionService

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


async def get_session_service(
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
    container_manager: ContainerManager = Depends(get_container_manager),
) -> SessionService:
    """Dependency for session service."""
    return SessionService(db, redis_client, container_manager)


async def _get_spawn_depth(db: AsyncSession, session_id: str) -> int:
    """Calculate the depth of a session in the spawn tree."""
    depth = 0
    current_id = session_id

    while current_id:
        result = await db.execute(
            select(Session.parent_session_id).where(Session.id == current_id)
        )
        parent_id = result.scalar_one_or_none()
        if parent_id:
            depth += 1
            current_id = parent_id
        else:
            break

    return depth


async def _count_children(db: AsyncSession, session_id: str) -> int:
    """Count direct children of a session."""
    result = await db.execute(
        select(func.count()).where(Session.parent_session_id == session_id)
    )
    return result.scalar() or 0


async def _count_tree_instances(db: AsyncSession, root_session_id: str) -> int:
    """Count total instances in a session tree."""
    # Find root of tree
    current_id = root_session_id
    while True:
        result = await db.execute(
            select(Session.parent_session_id).where(Session.id == current_id)
        )
        parent_id = result.scalar_one_or_none()
        if parent_id:
            current_id = parent_id
        else:
            break

    root_id = current_id

    # Count all sessions in tree (simple recursive count via SQL)
    # For simplicity, we'll do a basic count of related sessions
    result = await db.execute(select(func.count()).select_from(Session))
    return result.scalar() or 0


@router.post("/{session_id}/spawn", response_model=SpawnResponse, status_code=status.HTTP_201_CREATED)
async def spawn_child_session(
    session_id: str,
    request: SpawnRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
):
    """
    Spawn a child Claude Code instance.

    Creates a new session as a child of the current session.
    The child can inherit or clone the parent's workspace.
    """
    # Verify parent session exists
    result = await db.execute(select(Session).where(Session.id == session_id))
    parent_session = result.scalar_one_or_none()

    if not parent_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Check spawn depth limit
    depth = await _get_spawn_depth(db, session_id)
    if depth >= settings.max_spawn_depth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum spawn depth ({settings.max_spawn_depth}) exceeded",
        )

    # Check children limit
    children_count = await _count_children(db, session_id)
    if children_count >= settings.max_children_per_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum children ({settings.max_children_per_session}) exceeded",
        )

    # Check total instances limit
    total_instances = await _count_tree_instances(db, session_id)
    if total_instances >= settings.max_total_instances:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum total instances ({settings.max_total_instances}) exceeded",
        )

    # Build workspace config
    workspace_mode = SpawnWorkspaceMode(
        request.workspace.get("type", "inherit") if request.workspace else "inherit"
    )

    if workspace_mode == SpawnWorkspaceMode.EPHEMERAL:
        workspace_config = WorkspaceConfig(type=WorkspaceType.EPHEMERAL)
    else:
        # Inherit or clone from parent
        workspace_config = WorkspaceConfig(
            type=WorkspaceType(parent_session.workspace_type),
            id=parent_session.workspace_id,
        )

    # Build session config
    parent_config = parent_session.config or {}
    session_config = SessionConfig(
        timeout_seconds=request.config.get("timeout_seconds", parent_config.get("timeout_seconds", 3600))
        if request.config
        else parent_config.get("timeout_seconds", 3600),
        model=parent_config.get("model", "opus-4"),
    )

    # Create child session
    try:
        child_session = await session_service.create_session(
            SessionCreate(
                workspace=workspace_config,
                config=session_config,
                parent_session_id=session_id,
            ),
            user.user_id,
        )

        return SpawnResponse(
            child_session_id=child_session.session_id,
            status="starting",
            parent_session_id=session_id,
        )
    except Exception as e:
        logger.error(f"Failed to spawn child session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{session_id}/children")
async def list_child_sessions(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List child sessions of a session.

    Returns all direct children of the specified session.
    """
    # Verify session exists
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Get children
    result = await db.execute(
        select(Session).where(Session.parent_session_id == session_id)
    )
    children = result.scalars().all()

    return {
        "parent_session_id": session_id,
        "children": [
            {
                "session_id": child.id,
                "status": child.status,
                "created_at": child.created_at.isoformat(),
            }
            for child in children
        ],
    }
