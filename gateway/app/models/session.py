"""Session-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    """Session status enum."""

    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    STOPPED = "stopped"
    FAILED = "failed"


class WorkspaceType(str, Enum):
    """Workspace type enum."""

    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"


class WorkspaceConfig(BaseModel):
    """Workspace configuration."""

    type: WorkspaceType = WorkspaceType.EPHEMERAL
    id: Optional[str] = None
    git_repo: Optional[str] = None
    git_branch: Optional[str] = "main"


class SessionConfig(BaseModel):
    """Session configuration."""

    timeout_seconds: int = 3600
    model: str = "opus-4"
    system_prompt: Optional[str] = None
    allowed_tools: List[str] = Field(default_factory=lambda: ["*"])
    mcp_servers: Dict[str, Any] = Field(default_factory=dict)


class SessionCreate(BaseModel):
    """Request body for creating a session."""

    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    config: SessionConfig = Field(default_factory=SessionConfig)
    parent_session_id: Optional[str] = None


class SessionResponse(BaseModel):
    """Response for session operations."""

    session_id: str
    status: SessionStatus
    container_id: Optional[str] = None
    created_at: datetime
    websocket_url: Optional[str] = None


class SessionDetail(BaseModel):
    """Detailed session information."""

    session_id: str
    status: SessionStatus
    container_id: Optional[str] = None
    created_at: datetime
    last_activity: Optional[datetime] = None
    parent_session_id: Optional[str] = None
    child_session_ids: List[str] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_turns: int = 0


class SessionList(BaseModel):
    """Paginated list of sessions."""

    sessions: List[SessionDetail]
    total: int
    limit: int
    offset: int
