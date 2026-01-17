"""Message-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MessageStatus(str, Enum):
    """Message processing status."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatRequest(BaseModel):
    """Request body for sending a chat message."""

    prompt: str
    stream: bool = True
    timeout_seconds: Optional[int] = None


class ChatResponse(BaseModel):
    """Response for chat operations."""

    message_id: str
    status: MessageStatus


class UsageInfo(BaseModel):
    """Token usage information."""

    input_tokens: int = 0
    output_tokens: int = 0


class ChatResult(BaseModel):
    """Complete chat result."""

    message_id: str
    status: MessageStatus = MessageStatus.COMPLETED
    type: str = "result"
    subtype: str = "success"
    result: Optional[str] = None
    duration_ms: Optional[int] = None
    usage: UsageInfo = Field(default_factory=UsageInfo)


class MessageDetail(BaseModel):
    """Detailed message information."""

    message_id: str
    status: MessageStatus
    result: Optional[ChatResult] = None


# WebSocket message types


class WSMessageType(str, Enum):
    """WebSocket message types."""

    PROMPT = "prompt"
    PING = "ping"
    PONG = "pong"
    ASSISTANT = "assistant"
    TOOL_USE = "tool_use"
    RESULT = "result"
    SYSTEM = "system"
    CHILD_RESULT = "child_result"
    ERROR = "error"


class WSClientMessage(BaseModel):
    """Message from WebSocket client."""

    type: WSMessageType
    prompt: Optional[str] = None


class WSServerMessage(BaseModel):
    """Message to WebSocket client."""

    type: WSMessageType
    message: Optional[Dict[str, Any]] = None
    tool: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    subtype: Optional[str] = None
    result: Optional[str] = None
    usage: Optional[UsageInfo] = None
    event: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    child_session_id: Optional[str] = None
