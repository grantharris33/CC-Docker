"""Container-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel


class ContainerStatus(str, Enum):
    """Container status enum."""

    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class ContainerInfo(BaseModel):
    """Container information."""

    container_id: str
    status: ContainerStatus
    session_id: str
    created_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None


class ContainerStats(BaseModel):
    """Container resource statistics."""

    cpu_percent: float = 0.0
    memory_usage_bytes: int = 0
    memory_limit_bytes: int = 0
    network_rx_bytes: int = 0
    network_tx_bytes: int = 0


class SpawnRequest(BaseModel):
    """Request body for spawning a child session."""

    prompt: str
    workspace: Optional[Dict] = None
    config: Optional[Dict] = None
    callback: Optional[Dict] = None


class SpawnWorkspaceMode(str, Enum):
    """Workspace mode for child sessions."""

    INHERIT = "inherit"
    CLONE = "clone"
    EPHEMERAL = "ephemeral"


class SpawnResponse(BaseModel):
    """Response for spawn operations."""

    child_session_id: str
    status: str = "starting"
    parent_session_id: str
