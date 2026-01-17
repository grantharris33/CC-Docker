"""Discord bot service for CC-Docker."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import discord
from discord.ext import tasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import get_db_session
from app.db.models import DiscordInteraction, Session as SessionModel

logger = logging.getLogger(__name__)
settings = get_settings()


class CCDiscordBot(discord.Client):
    """Discord bot for CC-Docker interactions."""

    def __init__(self, channel_id: int, redis_client):
        """Initialize Discord bot.

        Args:
            channel_id: Discord channel ID to post to
            redis_client: Redis client for pub/sub communication
        """
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.messages = True

        super().__init__(intents=intents)

        self.channel_id = channel_id
        self.redis = redis_client
        self.channel: Optional[discord.TextChannel] = None
        self.update_task_started = False

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f"Discord bot connected as {self.user}")

        # Get the channel
        self.channel = self.get_channel(self.channel_id)
        if not self.channel:
            logger.error(f"Could not find channel with ID {self.channel_id}")
            return

        logger.info(f"Monitoring channel: #{self.channel.name} ({self.channel_id})")

        # Start the periodic update task
        if not self.update_task_started:
            self.update_countdowns.start()
            self.update_task_started = True

    async def on_message(self, message: discord.Message):
        """Handle incoming messages."""
        # Ignore messages from the bot itself
        if message.author == self.user:
            return

        # Only process messages in threads
        if not isinstance(message.channel, discord.Thread):
            return

        # Check if this thread is tracking a question
        thread_id = str(message.channel.id)

        async for db in get_db_session():
            try:
                # Find the interaction for this thread
                result = await db.execute(
                    select(DiscordInteraction)
                    .where(DiscordInteraction.discord_thread_id == thread_id)
                    .where(DiscordInteraction.status == "pending")
                )
                interaction = result.scalar_one_or_none()

                if not interaction:
                    return

                # Store the response
                interaction.response = message.content
                interaction.status = "answered"
                interaction.answered_at = datetime.utcnow()

                await db.commit()

                # Publish response to Redis for the waiting API call
                response_key = f"session:{interaction.session_id}:discord:response:{interaction.id}"
                await self.redis.set(response_key, message.content, ex=3600)  # 1 hour expiry

                # Acknowledge in Discord
                await message.add_reaction("✅")
                await message.channel.send(f"✅ Response received: `{message.content[:100]}{'...' if len(message.content) > 100 else ''}`")

                logger.info(f"Response received for interaction {interaction.id}: {message.content[:50]}")

            except Exception as e:
                logger.error(f"Error handling message: {e}", exc_info=True)
            finally:
                await db.close()

    @tasks.loop(seconds=settings.discord_update_interval)
    async def update_countdowns(self):
        """Periodically update countdown timers in questions."""
        try:
            async for db in get_db_session():
                try:
                    # Find all pending interactions
                    result = await db.execute(
                        select(DiscordInteraction)
                        .where(DiscordInteraction.status == "pending")
                        .where(DiscordInteraction.interaction_type == "question")
                    )
                    interactions = result.scalars().all()

                    for interaction in interactions:
                        await self._update_countdown(interaction, db)

                except Exception as e:
                    logger.error(f"Error updating countdowns: {e}", exc_info=True)
                finally:
                    await db.close()

        except Exception as e:
            logger.error(f"Error in update_countdowns task: {e}", exc_info=True)

    async def _update_countdown(self, interaction: DiscordInteraction, db: AsyncSession):
        """Update countdown for a specific interaction."""
        try:
            # Calculate time remaining
            now = datetime.utcnow()
            created = interaction.created_at
            timeout = timedelta(seconds=interaction.timeout_seconds)
            elapsed = now - created
            remaining = timeout - elapsed

            # Check if timed out
            if remaining.total_seconds() <= 0:
                # Don't update if already handled by retry logic
                return

            # Only update if message exists and significant time has passed (e.g., > 1 minute since creation)
            if not interaction.discord_message_id or elapsed.total_seconds() < 60:
                return

            # Get the thread
            if not self.channel:
                return

            thread = self.channel.get_thread(int(interaction.discord_thread_id))
            if not thread:
                # Try fetching if not in cache
                try:
                    thread = await self.channel.fetch_thread(int(interaction.discord_thread_id))
                except discord.NotFound:
                    logger.warning(f"Thread {interaction.discord_thread_id} not found")
                    return

            # Get the original message
            try:
                message = await thread.fetch_message(int(interaction.discord_message_id))
            except discord.NotFound:
                logger.warning(f"Message {interaction.discord_message_id} not found")
                return

            # Update the message with new countdown
            minutes_remaining = int(remaining.total_seconds() / 60)
            updated_content = self._format_question_message(
                interaction.session_id,
                interaction.message,
                minutes_remaining,
                interaction.attempt,
                interaction.max_attempts,
                interaction.priority
            )

            await message.edit(content=updated_content)

        except Exception as e:
            logger.error(f"Error updating countdown for interaction {interaction.id}: {e}", exc_info=True)

    async def post_question(
        self,
        session_id: str,
        question: str,
        interaction_id: str,
        timeout_seconds: int,
        attempt: int = 1,
        max_attempts: int = 3,
        priority: str = "normal"
    ) -> tuple[str, str]:
        """Post a question to Discord and create a thread.

        Args:
            session_id: Session ID asking the question
            question: The question text
            interaction_id: Interaction ID for tracking
            timeout_seconds: Timeout in seconds
            attempt: Current attempt number
            max_attempts: Maximum number of attempts
            priority: Priority level ('normal' or 'urgent')

        Returns:
            Tuple of (thread_id, message_id)
        """
        if not self.channel:
            raise RuntimeError("Discord bot not ready - channel not available")

        # Calculate timeout in minutes for display
        minutes = int(timeout_seconds / 60)

        # Format the message
        content = self._format_question_message(
            session_id, question, minutes, attempt, max_attempts, priority
        )

        # Post the message
        message = await self.channel.send(content)

        # Create a thread for responses
        thread_name = f"Session {session_id[:8]} - Question"
        if attempt > 1:
            thread_name += f" (Retry {attempt})"

        thread = await message.create_thread(name=thread_name[:100])  # Discord limit

        # Post instructions in the thread
        await thread.send(
            f"📝 **Reply in this thread to answer the question.**\n\n"
            f"⏱️ This question will timeout in {minutes} minutes.\n"
            f"🔄 If no response, will retry {max_attempts - attempt} more time(s)."
        )

        logger.info(f"Posted question for session {session_id} (attempt {attempt}/{max_attempts})")

        return str(thread.id), str(message.id)

    async def post_notification(
        self,
        session_id: str,
        message: str,
        priority: str = "normal",
        summary: Optional[str] = None
    ):
        """Post a notification to Discord.

        Args:
            session_id: Session ID sending the notification
            message: Notification message
            priority: Priority level ('normal' or 'urgent')
            summary: Optional summary or additional details
        """
        if not self.channel:
            raise RuntimeError("Discord bot not ready - channel not available")

        # Choose emoji based on priority
        emoji = "⚠️" if priority == "urgent" else "✅"

        # Format the message
        content = f"{emoji} **Session {session_id[:8]} Notification**\n\n{message}"

        if summary:
            content += f"\n\n**Summary:**\n{summary}"

        content += f"\n\n_Session: {session_id} | Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"

        # Post the message
        await self.channel.send(content)

        logger.info(f"Posted notification for session {session_id} (priority: {priority})")

    async def post_retry_message(
        self,
        thread_id: str,
        question: str,
        timeout_minutes: int,
        attempt: int,
        max_attempts: int
    ):
        """Post a retry message in an existing thread.

        Args:
            thread_id: Discord thread ID
            question: Original question
            timeout_minutes: Timeout in minutes
            attempt: Current attempt number
            max_attempts: Maximum number of attempts
        """
        if not self.channel:
            raise RuntimeError("Discord bot not ready - channel not available")

        # Get the thread
        thread = self.channel.get_thread(int(thread_id))
        if not thread:
            try:
                thread = await self.channel.fetch_thread(int(thread_id))
            except discord.NotFound:
                logger.error(f"Thread {thread_id} not found for retry message")
                return

        # Post retry message
        emoji = "⏰" if attempt < max_attempts else "🚨"
        content = (
            f"{emoji} **Still waiting for response...**\n\n"
            f"Original question: {question}\n\n"
            f"⏱️ Timeout: {timeout_minutes} minutes remaining (Attempt {attempt}/{max_attempts})\n"
            f"📝 Reply in this thread to answer"
        )

        if attempt == max_attempts:
            content += f"\n\n⚠️ **This is the final attempt - session will fail if no response.**"

        await thread.send(content)

        logger.info(f"Posted retry message in thread {thread_id} (attempt {attempt}/{max_attempts})")

    def _format_question_message(
        self,
        session_id: str,
        question: str,
        minutes_remaining: int,
        attempt: int,
        max_attempts: int,
        priority: str
    ) -> str:
        """Format a question message."""
        emoji = "🚨" if priority == "urgent" else "🤔"

        content = (
            f"{emoji} **Question from Session {session_id[:8]}**\n\n"
            f"{question}\n\n"
            f"⏱️ Timeout: {minutes_remaining} minutes remaining (Attempt {attempt}/{max_attempts})\n"
            f"📝 Reply in the thread to answer\n\n"
            f"_Session: {session_id} | Created: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
        )

        return content


# Global bot instance
_bot_instance: Optional[CCDiscordBot] = None
_bot_task: Optional[asyncio.Task] = None


async def start_discord_bot(redis_client):
    """Start the Discord bot.

    Args:
        redis_client: Redis client for pub/sub communication
    """
    global _bot_instance, _bot_task

    if not settings.discord_bot_token or not settings.discord_channel_id:
        logger.warning("Discord bot not configured - skipping initialization")
        return

    if _bot_instance:
        logger.warning("Discord bot already running")
        return

    try:
        _bot_instance = CCDiscordBot(
            channel_id=int(settings.discord_channel_id),
            redis_client=redis_client
        )

        # Start the bot in the background
        _bot_task = asyncio.create_task(_bot_instance.start(settings.discord_bot_token))

        logger.info("Discord bot starting...")

    except Exception as e:
        logger.error(f"Failed to start Discord bot: {e}", exc_info=True)
        _bot_instance = None
        _bot_task = None


async def stop_discord_bot():
    """Stop the Discord bot."""
    global _bot_instance, _bot_task

    if _bot_instance:
        try:
            await _bot_instance.close()
            logger.info("Discord bot stopped")
        except Exception as e:
            logger.error(f"Error stopping Discord bot: {e}", exc_info=True)
        finally:
            _bot_instance = None

    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
        _bot_task = None


def get_discord_bot() -> Optional[CCDiscordBot]:
    """Get the Discord bot instance.

    Returns:
        Discord bot instance or None if not running
    """
    return _bot_instance
