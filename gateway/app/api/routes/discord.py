"""Discord interaction API routes."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_redis
from app.db.database import get_db
from app.db.models import DiscordInteraction, Session as SessionModel
from app.services.discord import get_discord_bot

logger = logging.getLogger(__name__)

router = APIRouter()


class NotifyRequest(BaseModel):
    """Request to send a notification."""

    session_id: str = Field(..., description="Session ID sending the notification")
    message: str = Field(..., description="Notification message", min_length=1, max_length=2000)
    priority: str = Field("normal", description="Priority level: 'normal' or 'urgent'")
    summary: Optional[str] = Field(None, description="Optional summary or additional details", max_length=4000)


class NotifyResponse(BaseModel):
    """Response from notification."""

    success: bool
    interaction_id: str


class AskRequest(BaseModel):
    """Request to ask a question."""

    session_id: str = Field(..., description="Session ID asking the question")
    question: str = Field(..., description="Question text", min_length=1, max_length=2000)
    timeout_seconds: int = Field(1800, description="Timeout in seconds (default: 30 minutes)", ge=60, le=7200)
    max_attempts: int = Field(3, description="Maximum retry attempts", ge=1, le=5)
    priority: str = Field("normal", description="Priority level: 'normal' or 'urgent'")
    options: Optional[list[str]] = Field(None, description="Optional quick reply options")


class AskResponse(BaseModel):
    """Response from ask question."""

    interaction_id: str
    status: str
    response: Optional[str] = None
    timed_out: bool = False


@router.post("/notify", response_model=NotifyResponse)
async def notify_user(
    request: NotifyRequest,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
    user_id: str = Depends(get_current_user),
):
    """Send a notification to the user via Discord.

    This is a fire-and-forget operation - the notification is posted and the
    request returns immediately without waiting for any user action.
    """
    # Get Discord bot
    bot = get_discord_bot()
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discord bot not available"
        )

    # Verify session exists
    result = await db.execute(
        select(SessionModel).where(SessionModel.id == request.session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found"
        )

    # Create interaction record
    interaction_id = str(uuid4())
    interaction = DiscordInteraction(
        id=interaction_id,
        session_id=request.session_id,
        interaction_type="notification",
        message=request.message,
        status="completed",  # Notifications are immediately complete
        timeout_seconds=0,  # No timeout for notifications
        priority=request.priority,
        created_at=datetime.utcnow(),
    )

    db.add(interaction)
    await db.commit()

    # Post to Discord
    try:
        await bot.post_notification(
            session_id=request.session_id,
            message=request.message,
            priority=request.priority,
            summary=request.summary
        )
    except Exception as e:
        logger.error(f"Failed to post notification to Discord: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to post notification: {str(e)}"
        )

    return NotifyResponse(success=True, interaction_id=interaction_id)


@router.post("/ask", response_model=AskResponse)
async def ask_user(
    request: AskRequest,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
    user_id: str = Depends(get_current_user),
):
    """Ask the user a question via Discord and wait for response.

    This endpoint BLOCKS until:
    1. User responds in Discord thread
    2. Timeout is reached (will retry up to max_attempts)
    3. All retry attempts fail

    The timeout and retry logic works as follows:
    - Attempt 1: Post question, wait timeout_seconds
    - If timeout: Post retry message, wait timeout_seconds again
    - Repeat for max_attempts total
    - If all attempts timeout: Return with timed_out=True
    """
    # Get Discord bot
    bot = get_discord_bot()
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Discord bot not available"
        )

    # Verify session exists
    result = await db.execute(
        select(SessionModel).where(SessionModel.id == request.session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found"
        )

    # Create interaction record
    interaction_id = str(uuid4())
    interaction = DiscordInteraction(
        id=interaction_id,
        session_id=request.session_id,
        interaction_type="question",
        message=request.question,
        status="pending",
        timeout_seconds=request.timeout_seconds,
        max_attempts=request.max_attempts,
        priority=request.priority,
        created_at=datetime.utcnow(),
    )

    db.add(interaction)
    await db.commit()

    # Retry loop
    for attempt in range(1, request.max_attempts + 1):
        try:
            # Update attempt number
            interaction.attempt = attempt
            await db.commit()

            # Post question or retry message
            if attempt == 1:
                # First attempt: post new question
                thread_id, message_id = await bot.post_question(
                    session_id=request.session_id,
                    question=request.question,
                    interaction_id=interaction_id,
                    timeout_seconds=request.timeout_seconds,
                    attempt=attempt,
                    max_attempts=request.max_attempts,
                    priority=request.priority
                )

                # Store Discord IDs
                interaction.discord_thread_id = thread_id
                interaction.discord_message_id = message_id
                await db.commit()

            else:
                # Retry: post message in existing thread
                minutes = int(request.timeout_seconds / 60)
                await bot.post_retry_message(
                    thread_id=interaction.discord_thread_id,
                    question=request.question,
                    timeout_minutes=minutes,
                    attempt=attempt,
                    max_attempts=request.max_attempts
                )

            # Wait for response with timeout
            response_key = f"session:{request.session_id}:discord:response:{interaction_id}"

            # Poll Redis for response
            timeout_at = datetime.utcnow() + timedelta(seconds=request.timeout_seconds)
            while datetime.utcnow() < timeout_at:
                # Check if response available
                response_value = await redis.get(response_key)
                if response_value:
                    # Response received!
                    response_text = response_value.decode('utf-8') if isinstance(response_value, bytes) else str(response_value)

                    # Update interaction
                    interaction.response = response_text
                    interaction.status = "answered"
                    interaction.answered_at = datetime.utcnow()
                    await db.commit()

                    logger.info(f"Question {interaction_id} answered: {response_text[:50]}")

                    return AskResponse(
                        interaction_id=interaction_id,
                        status="answered",
                        response=response_text,
                        timed_out=False
                    )

                # Sleep before next poll
                await asyncio.sleep(1)

            # Timeout reached for this attempt
            logger.warning(f"Question {interaction_id} timed out (attempt {attempt}/{request.max_attempts})")

        except Exception as e:
            logger.error(f"Error during ask attempt {attempt}: {e}", exc_info=True)
            # Continue to next attempt

    # All attempts failed
    interaction.status = "timeout"
    interaction.timeout_at = datetime.utcnow()
    await db.commit()

    logger.error(f"Question {interaction_id} failed after {request.max_attempts} attempts")

    return AskResponse(
        interaction_id=interaction_id,
        status="timeout",
        response=None,
        timed_out=True
    )


@router.get("/interactions/{interaction_id}")
async def get_interaction(
    interaction_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Get details of a Discord interaction."""
    result = await db.execute(
        select(DiscordInteraction).where(DiscordInteraction.id == interaction_id)
    )
    interaction = result.scalar_one_or_none()

    if not interaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interaction {interaction_id} not found"
        )

    return {
        "id": interaction.id,
        "session_id": interaction.session_id,
        "interaction_type": interaction.interaction_type,
        "message": interaction.message,
        "response": interaction.response,
        "status": interaction.status,
        "attempt": interaction.attempt,
        "max_attempts": interaction.max_attempts,
        "priority": interaction.priority,
        "created_at": interaction.created_at.isoformat(),
        "answered_at": interaction.answered_at.isoformat() if interaction.answered_at else None,
        "timeout_at": interaction.timeout_at.isoformat() if interaction.timeout_at else None,
    }
