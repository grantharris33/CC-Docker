"""Chat endpoints for sending messages to Claude Code sessions."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional, Union

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_redis
from app.core.security import User, get_current_user
from app.db.models import Message, Session
from app.models.message import (
    ChatRequest,
    ChatResponse,
    ChatResult,
    MessageDetail,
    MessageStatus,
    UsageInfo,
)
from app.models.session import SessionStatus
from app.services.pubsub import PubSubService, get_pubsub_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/{session_id}/chat", response_model=Union[ChatResponse, ChatResult])
async def send_chat_message(
    session_id: str,
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Send a message to a Claude Code session.

    If stream=true (default), returns immediately with message_id.
    Connect to the WebSocket to receive streaming output.

    If stream=false, blocks until the response is complete.
    """
    # Verify session exists and is ready
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    if session.status not in [SessionStatus.IDLE.value, SessionStatus.RUNNING.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session is not ready (status: {session.status})",
        )

    # Create message record
    message_id = str(uuid.uuid4())
    db_message = Message(
        id=message_id,
        session_id=session_id,
        role="user",
        content=request.prompt,
    )
    db.add(db_message)

    # Update session status
    session.status = SessionStatus.RUNNING.value
    session.updated_at = datetime.utcnow()
    await db.commit()

    # Push prompt to session's input queue
    pubsub = await get_pubsub_service(redis_client)
    await pubsub.push_input(session_id, request.prompt)

    if request.stream:
        # Return immediately for streaming
        return ChatResponse(
            message_id=message_id,
            status=MessageStatus.PROCESSING,
        )
    else:
        # Wait for result (blocking)
        return await _wait_for_result(
            session_id,
            message_id,
            pubsub,
            db,
            request.timeout_seconds or 600,
        )


async def _wait_for_result(
    session_id: str,
    message_id: str,
    pubsub: PubSubService,
    db: AsyncSession,
    timeout: int,
) -> ChatResult:
    """Wait for Claude Code to complete processing."""
    try:
        async with asyncio.timeout(timeout):
            async for message in pubsub.subscribe_session_output(session_id):
                if message.get("type") == "result":
                    data = message.get("data", {})

                    # Update message with result
                    result = await db.execute(
                        select(Message).where(Message.id == message_id)
                    )
                    db_message = result.scalar_one_or_none()
                    if db_message:
                        db_message.cost_usd = data.get("total_cost_usd", 0)
                        db_message.tokens_in = data.get("usage", {}).get(
                            "input_tokens", 0
                        )
                        db_message.tokens_out = data.get("usage", {}).get(
                            "output_tokens", 0
                        )
                        db_message.duration_ms = data.get("duration_ms")
                        await db.commit()

                    return ChatResult(
                        message_id=message_id,
                        type="result",
                        subtype=data.get("subtype", "success"),
                        result=data.get("result"),
                        duration_ms=data.get("duration_ms"),
                        total_cost_usd=data.get("total_cost_usd", 0),
                        usage=UsageInfo(
                            input_tokens=data.get("usage", {}).get("input_tokens", 0),
                            output_tokens=data.get("usage", {}).get("output_tokens", 0),
                        ),
                    )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Request timed out after {timeout} seconds",
        )


@router.get("/{session_id}/messages/{message_id}", response_model=MessageDetail)
async def get_message_status(
    session_id: str,
    message_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Get message status and result.

    Returns the current status of a message and its result if completed.
    """
    # Verify session exists
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Get message
    result = await db.execute(
        select(Message).where(
            Message.id == message_id, Message.session_id == session_id
        )
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message {message_id} not found",
        )

    # Check if still processing (check Redis for latest status)
    state = await redis_client.hgetall(f"session:{session_id}:state")
    session_status = state.get("status", session.status)

    if session_status == SessionStatus.RUNNING.value:
        return MessageDetail(
            message_id=message_id,
            status=MessageStatus.PROCESSING,
        )

    # Get result from database
    if message.duration_ms is not None:
        return MessageDetail(
            message_id=message_id,
            status=MessageStatus.COMPLETED,
            result=ChatResult(
                message_id=message_id,
                type="result",
                subtype="success",
                result=message.content,
                duration_ms=message.duration_ms,
                total_cost_usd=message.cost_usd,
                usage=UsageInfo(
                    input_tokens=message.tokens_in,
                    output_tokens=message.tokens_out,
                ),
            ),
        )

    return MessageDetail(
        message_id=message_id,
        status=MessageStatus.PROCESSING,
    )
