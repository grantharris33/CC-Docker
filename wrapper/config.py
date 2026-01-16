"""Wrapper configuration."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class WrapperConfig:
    """Configuration for the Claude Code wrapper."""

    session_id: str
    redis_url: str
    gateway_url: str
    parent_session_id: Optional[str] = None
    workspace_path: str = "/workspace"
    claude_model: str = "opus-4"

    @classmethod
    def from_env(cls) -> "WrapperConfig":
        """Create config from environment variables."""
        session_id = os.environ.get("SESSION_ID")
        if not session_id:
            raise ValueError("SESSION_ID environment variable is required")

        return cls(
            session_id=session_id,
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379"),
            gateway_url=os.environ.get("GATEWAY_URL", "http://gateway:8000"),
            parent_session_id=os.environ.get("PARENT_SESSION_ID"),
            workspace_path=os.environ.get("WORKSPACE_PATH", "/workspace"),
            claude_model=os.environ.get("CLAUDE_MODEL", "opus-4"),
        )
