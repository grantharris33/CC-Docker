"""Discord bot service for CC-Docker."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import discord
from discord import app_commands
from discord.ext import commands, tasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import get_db_session
from app.db.models import DiscordInteraction, Session as SessionModel, Task

logger = logging.getLogger(__name__)
settings = get_settings()


class CCDiscordBot(commands.Bot):
    """Discord bot for CC-Docker interactions with slash commands."""

    def __init__(self, channel_id: int, redis_client):
        """Initialize Discord bot.

        Args:
            channel_id: Discord channel ID to post to
            redis_client: Redis client for pub/sub communication
        """
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.messages = True

        super().__init__(command_prefix="/", intents=intents)

        self.channel_id = channel_id
        self.redis = redis_client
        self.channel: Optional[discord.TextChannel] = None
        self.update_task_started = False
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self):
        """Setup hook called before bot starts."""
        # Register slash commands
        await self.register_slash_commands()

    async def register_slash_commands(self):
        """Register all slash commands with Discord."""
        # Task management commands
        @self.tree.command(name="task-create", description="Create a new automated task")
        @app_commands.describe(
            name="Task name (lowercase with hyphens)",
            prompt="Task prompt template with {parameters}",
            description="Task description"
        )
        async def task_create(
            interaction: discord.Interaction,
            name: str,
            prompt: str,
            description: str = ""
        ):
            await self.handle_task_create(interaction, name, prompt, description)

        @self.tree.command(name="task-list", description="List all tasks")
        @app_commands.describe(
            task_type="Filter by task type",
            enabled="Filter by enabled status"
        )
        async def task_list(
            interaction: discord.Interaction,
            task_type: Optional[str] = None,
            enabled: Optional[bool] = None
        ):
            await self.handle_task_list(interaction, task_type, enabled)

        @self.tree.command(name="task-start", description="Start a task manually")
        @app_commands.describe(
            task_name="Name of the task to start"
        )
        async def task_start(interaction: discord.Interaction, task_name: str):
            await self.handle_task_start(interaction, task_name)

        @self.tree.command(name="task-stop", description="Stop a running task")
        @app_commands.describe(
            task_name="Name of the task to stop"
        )
        async def task_stop(interaction: discord.Interaction, task_name: str):
            await self.handle_task_stop(interaction, task_name)

        @self.tree.command(name="task-schedule", description="Schedule a task with cron")
        @app_commands.describe(
            task_name="Name of the task",
            cron="Cron expression (e.g., '0 9 * * *' for 9am daily)"
        )
        async def task_schedule(
            interaction: discord.Interaction,
            task_name: str,
            cron: str
        ):
            await self.handle_task_schedule(interaction, task_name, cron)

        @self.tree.command(name="session-vnc", description="Get VNC access link for a session")
        @app_commands.describe(
            session_id="Session ID to access"
        )
        async def session_vnc(interaction: discord.Interaction, session_id: str):
            await self.handle_session_vnc(interaction, session_id)

        logger.info("Slash commands registered")

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f"Discord bot connected as {self.user}")

        # Get the channel
        self.channel = self.get_channel(self.channel_id)
        if not self.channel:
            logger.error(f"Could not find channel with ID {self.channel_id}")
            return

        logger.info(f"Monitoring channel: #{self.channel.name} ({self.channel_id})")

        # Sync slash commands with Discord
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

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

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        """Handle slash command errors."""
        logger.error(f"Slash command error: {error}", exc_info=error)

        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {str(error)}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Error: {str(error)}", ephemeral=True)

    async def handle_task_create(
        self,
        interaction: discord.Interaction,
        name: str,
        prompt: str,
        description: str
    ):
        """Handle /task-create command."""
        await interaction.response.defer()

        try:
            from app.services.task import TaskService
            from app.models.task import TaskCreate, TaskConfig

            async for db in get_db_session():
                try:
                    task_service = TaskService(db)

                    task_data = TaskCreate(
                        task_name=name,
                        task_type="manual",
                        description=description,
                        template_prompt=prompt,
                        config=TaskConfig(),
                        owner_user_id=str(interaction.user.id)
                    )

                    task = await task_service.create_task(task_data)

                    await interaction.followup.send(
                        f"✅ **Task Created**\n\n"
                        f"Name: `{task.task_name}`\n"
                        f"ID: `{task.id}`\n"
                        f"Description: {task.description or 'None'}\n\n"
                        f"Use `/task-start {task.task_name}` to run it manually."
                    )

                finally:
                    await db.close()

        except Exception as e:
            logger.error(f"Error creating task: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to create task: {str(e)}")

    async def handle_task_list(
        self,
        interaction: discord.Interaction,
        task_type: Optional[str],
        enabled: Optional[bool]
    ):
        """Handle /task-list command."""
        await interaction.response.defer()

        try:
            from app.services.task import TaskService

            async for db in get_db_session():
                try:
                    task_service = TaskService(db)
                    tasks, total = await task_service.list_tasks(
                        owner_user_id=str(interaction.user.id),
                        task_type=task_type,
                        enabled=enabled,
                        limit=20
                    )

                    if not tasks:
                        await interaction.followup.send("📋 No tasks found.")
                        return

                    lines = ["📋 **Your Tasks**\n"]
                    for task in tasks:
                        status = "✅" if task.enabled else "⏸️"
                        schedule = f" | `{task.schedule_cron}`" if task.schedule_cron else ""
                        lines.append(
                            f"{status} **{task.task_name}** ({task.task_type}){schedule}\n"
                            f"   Runs: {task.run_count} | Success: {task.success_count} | "
                            f"Failed: {task.failure_count}"
                        )

                    lines.append(f"\n_Total: {total} tasks_")

                    await interaction.followup.send("\n".join(lines))

                finally:
                    await db.close()

        except Exception as e:
            logger.error(f"Error listing tasks: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to list tasks: {str(e)}")

    async def handle_task_start(self, interaction: discord.Interaction, task_name: str):
        """Handle /task-start command."""
        await interaction.response.defer()

        try:
            from app.services.task import TaskService

            async for db in get_db_session():
                try:
                    task_service = TaskService(db)
                    task = await task_service.get_task(task_name=task_name)

                    if not task:
                        await interaction.followup.send(f"❌ Task `{task_name}` not found.")
                        return

                    # Start task with empty parameters (use defaults)
                    task_run, filled_prompt = await task_service.start_task(
                        task_id=task.id,
                        parameters=task.optional_parameters or {},
                        trigger="manual",
                        triggered_by_user_id=str(interaction.user.id)
                    )

                    await interaction.followup.send(
                        f"🚀 **Task Started**\n\n"
                        f"Task: `{task.task_name}`\n"
                        f"Run ID: `{task_run.id}`\n"
                        f"Status: {task_run.status}\n\n"
                        f"Monitor progress in this channel."
                    )

                finally:
                    await db.close()

        except Exception as e:
            logger.error(f"Error starting task: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to start task: {str(e)}")

    async def handle_task_stop(self, interaction: discord.Interaction, task_name: str):
        """Handle /task-stop command."""
        await interaction.response.defer()
        await interaction.followup.send(
            f"⚠️ Task stop not yet implemented. Task: `{task_name}`"
        )

    async def handle_task_schedule(
        self,
        interaction: discord.Interaction,
        task_name: str,
        cron: str
    ):
        """Handle /task-schedule command."""
        await interaction.response.defer()

        try:
            from app.services.task import TaskService
            from app.services.scheduler import SchedulerService
            from app.models.task import TaskUpdate

            async for db in get_db_session():
                try:
                    task_service = TaskService(db)
                    scheduler = SchedulerService()

                    task = await task_service.get_task(task_name=task_name)

                    if not task:
                        await interaction.followup.send(f"❌ Task `{task_name}` not found.")
                        return

                    # Validate cron expression
                    if not scheduler.validate_cron(cron):
                        await interaction.followup.send(
                            f"❌ Invalid cron expression: `{cron}`\n\n"
                            f"Example: `0 9 * * *` = daily at 9:00 AM"
                        )
                        return

                    # Update task schedule
                    update_data = TaskUpdate(schedule_cron=cron)
                    task = await task_service.update_task(task.id, update_data)

                    # Add to scheduler
                    await scheduler.add_task_schedule(task, db)

                    # Get next run times
                    next_runs = await scheduler.get_next_run_times(cron, count=3)
                    next_times = "\n".join([f"  • {t.strftime('%Y-%m-%d %H:%M:%S')}" for t in next_runs])

                    await interaction.followup.send(
                        f"⏰ **Task Scheduled**\n\n"
                        f"Task: `{task.task_name}`\n"
                        f"Schedule: `{cron}`\n\n"
                        f"**Next 3 runs:**\n{next_times}"
                    )

                finally:
                    await db.close()

        except Exception as e:
            logger.error(f"Error scheduling task: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to schedule task: {str(e)}")

    async def handle_session_vnc(self, interaction: discord.Interaction, session_id: str):
        """Handle /session-vnc command."""
        await interaction.response.defer(ephemeral=True)

        try:
            # TODO: Generate temporary VNC access token
            vnc_url = f"{settings.gateway_url}/vnc/{session_id}"

            await interaction.followup.send(
                f"🖥️ **VNC Access**\n\n"
                f"Session: `{session_id}`\n"
                f"VNC URL: {vnc_url}\n\n"
                f"⚠️ This link provides desktop access to the session container.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error getting VNC link: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to get VNC link: {str(e)}", ephemeral=True)

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
