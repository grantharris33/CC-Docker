"""Session management service."""

import logging
import os
import tempfile
import uuid
from datetime import datetime
from typing import List, Optional

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Message, Session
from app.models.session import (
    SessionConfig,
    SessionCreate,
    SessionDetail,
    SessionResponse,
    SessionStatus,
    WorkspaceConfig,
)
from app.services.container import ContainerManager

logger = logging.getLogger(__name__)
settings = get_settings()


class SessionService:
    """Service for managing Claude Code sessions."""

    def __init__(
        self,
        db: AsyncSession,
        redis_client: redis.Redis,
        container_manager: ContainerManager,
    ):
        self.db = db
        self.redis = redis_client
        self.container_manager = container_manager

    async def create_session(
        self, request: SessionCreate, user_id: str
    ) -> SessionResponse:
        """Create a new Claude Code session."""
        session_id = str(uuid.uuid4())

        # Create workspace directory
        workspace_path = self._create_workspace(
            session_id, request.workspace
        )

        # Build environment variables for container
        environment = {
            "SESSION_ID": session_id,
            "REDIS_URL": settings.redis_url,
            "GATEWAY_URL": "http://gateway:8000",
        }

        if request.parent_session_id:
            environment["PARENT_SESSION_ID"] = request.parent_session_id

        # Create container
        container_info = await self.container_manager.create_container(
            session_id=session_id,
            workspace_path=workspace_path,
            environment=environment,
            claude_config_path=settings.claude_config_path,
        )

        # Create database record
        db_session = Session(
            id=session_id,
            status=SessionStatus.STARTING,
            container_id=container_info.container_id,
            parent_session_id=request.parent_session_id,
            workspace_type=request.workspace.type.value,
            workspace_id=request.workspace.id,
            config=request.config.model_dump(),
        )
        self.db.add(db_session)
        await self.db.commit()

        # Store session state in Redis
        await self.redis.hset(
            f"session:{session_id}:state",
            mapping={
                "status": SessionStatus.STARTING,
                "container_id": container_info.container_id,
                "last_heartbeat": datetime.utcnow().isoformat(),
            },
        )

        # Add to active sessions set
        await self.redis.sadd("active_sessions", session_id)

        # Start container
        await self.container_manager.start_container(container_info.container_id)

        # Wait for startup
        started = await self.container_manager.wait_for_startup(
            container_info.container_id
        )

        if started:
            await self._update_status(session_id, SessionStatus.IDLE)
        else:
            await self._update_status(session_id, SessionStatus.FAILED)
            raise RuntimeError(f"Container failed to start for session {session_id}")

        return SessionResponse(
            session_id=session_id,
            status=SessionStatus.IDLE,
            container_id=container_info.container_id,
            created_at=datetime.utcnow(),
            websocket_url=f"ws://localhost:8000/api/v1/sessions/{session_id}/stream",
        )

    async def get_session(self, session_id: str) -> Optional[SessionDetail]:
        """Get session details."""
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return None

        # Get child session IDs
        child_result = await self.db.execute(
            select(Session.id).where(Session.parent_session_id == session_id)
        )
        child_ids = [row[0] for row in child_result.fetchall()]

        return SessionDetail(
            session_id=session.id,
            status=SessionStatus(session.status),
            container_id=session.container_id,
            created_at=session.created_at,
            last_activity=session.updated_at,
            parent_session_id=session.parent_session_id,
            child_session_ids=child_ids,
            total_cost_usd=session.total_cost_usd,
            total_turns=session.total_turns,
        )

    async def list_sessions(
        self,
        user_id: str,
        status: Optional[SessionStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[SessionDetail], int]:
        """List sessions with optional filtering."""
        query = select(Session)

        if status:
            query = query.where(Session.status == status.value)

        # Get total count
        count_result = await self.db.execute(
            select(Session.id).where(Session.status == status.value if status else True)
        )
        total = len(count_result.fetchall())

        # Get paginated results
        query = query.order_by(Session.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        sessions = result.scalars().all()

        details = []
        for session in sessions:
            detail = await self.get_session(session.id)
            if detail:
                details.append(detail)

        return details, total

    async def stop_session(self, session_id: str) -> SessionDetail:
        """Stop a session and its container."""
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.container_id:
            await self.container_manager.stop_container(session.container_id)

        await self._update_status(session_id, SessionStatus.STOPPED)

        # Remove from active sessions
        await self.redis.srem("active_sessions", session_id)

        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and cleanup resources."""
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Stop and remove container
        if session.container_id:
            await self.container_manager.stop_container(session.container_id)
            await self.container_manager.remove_container(
                session.container_id, force=True
            )

        # Remove from Redis
        await self.redis.delete(f"session:{session_id}:state")
        await self.redis.delete(f"session:{session_id}:input")
        await self.redis.srem("active_sessions", session_id)

        # Delete from database
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        db_session = result.scalar_one_or_none()
        if db_session:
            await self.db.delete(db_session)
            await self.db.commit()

    async def _update_status(
        self, session_id: str, status: SessionStatus
    ) -> None:
        """Update session status in both database and Redis."""
        # Update database
        result = await self.db.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.status = status.value
            session.updated_at = datetime.utcnow()
            if status == SessionStatus.STOPPED:
                session.stopped_at = datetime.utcnow()
            await self.db.commit()

        # Update Redis
        await self.redis.hset(f"session:{session_id}:state", "status", status.value)

    def _create_workspace(
        self, session_id: str, workspace: WorkspaceConfig
    ) -> str:
        """Create workspace directory for session."""
        base_path = os.path.join(tempfile.gettempdir(), "cc-docker-workspaces")
        os.makedirs(base_path, exist_ok=True)

        workspace_path = os.path.join(base_path, session_id)
        os.makedirs(workspace_path, exist_ok=True)

        return workspace_path
