"""Pushover notification service."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import requests
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PushoverNotification, TaskRun
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class PushoverService:
    """Service for sending Pushover notifications."""

    PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"

    def __init__(self, db: AsyncSession):
        """Initialize Pushover service."""
        self.db = db
        self.settings = get_settings()
        self.api_token = getattr(self.settings, "PUSHOVER_API_TOKEN", None)

    async def send_notification(
        self,
        user_key: str,
        message: str,
        title: Optional[str] = None,
        priority: int = 0,
        url: Optional[str] = None,
        url_title: Optional[str] = None,
        task_run_id: Optional[str] = None,
    ) -> dict:
        """
        Send a Pushover notification.

        Args:
            user_key: User's Pushover key
            message: Notification message
            title: Notification title
            priority: Priority level (-2 to 2)
            url: URL to attach
            url_title: Title for URL
            task_run_id: Associated task run ID

        Returns:
            Response from Pushover API
        """
        if not self.api_token:
            logger.warning("PUSHOVER_API_TOKEN not configured, skipping notification")
            return {"status": 0, "error": "Pushover not configured"}

        # Build request data
        data = {
            "token": self.api_token,
            "user": user_key,
            "message": message,
            "priority": priority,
        }

        if title:
            data["title"] = title
        if url:
            data["url"] = url
        if url_title:
            data["url_title"] = url_title

        # Send to Pushover
        try:
            response = requests.post(self.PUSHOVER_API_URL, data=data, timeout=10)
            response_json = response.json()

            # Log notification
            await self._log_notification(
                task_run_id=task_run_id,
                user_key=user_key,
                message=message,
                priority=priority,
                pushover_response=response_json,
                success=response_json.get("status") == 1,
            )

            if response_json.get("status") == 1:
                logger.info(f"Sent Pushover notification to {user_key[:8]}...")
            else:
                logger.error(f"Pushover error: {response_json.get('errors')}")

            return response_json

        except requests.RequestException as e:
            logger.error(f"Failed to send Pushover notification: {e}")
            await self._log_notification(
                task_run_id=task_run_id,
                user_key=user_key,
                message=message,
                priority=priority,
                pushover_response={"error": str(e)},
                success=False,
            )
            return {"status": 0, "error": str(e)}

    async def send_task_failure_notification(
        self,
        task_run: TaskRun,
        task_name: str,
        user_key: str,
        discord_thread_url: Optional[str] = None,
    ):
        """Send notification for task failure."""
        message = (
            f"Task '{task_name}' failed after {task_run.retry_count + 1} attempts.\n\n"
            f"Error: {task_run.error_message or 'Unknown error'}"
        )

        await self.send_notification(
            user_key=user_key,
            message=message,
            title=f"🚨 CC-Docker: {task_name} Failed",
            priority=1,  # High priority
            url=discord_thread_url,
            url_title="View in Discord",
            task_run_id=task_run.id,
        )

    async def send_task_intervention_notification(
        self,
        task_run: TaskRun,
        task_name: str,
        user_key: str,
        intervention_reason: str,
        vnc_url: Optional[str] = None,
        discord_thread_url: Optional[str] = None,
    ):
        """Send notification for human intervention required."""
        message = (
            f"Task '{task_name}' requires manual intervention.\n\n"
            f"Reason: {intervention_reason}\n\n"
            f"Use VNC to resolve: /session-vnc {task_run.session_id}"
        )

        await self.send_notification(
            user_key=user_key,
            message=message,
            title=f"⚠️ CC-Docker: Intervention Needed",
            priority=1,  # High priority
            url=vnc_url or discord_thread_url,
            url_title="Open VNC" if vnc_url else "View in Discord",
            task_run_id=task_run.id,
        )

    async def send_task_complete_notification(
        self,
        task_run: TaskRun,
        task_name: str,
        user_key: str,
        discord_thread_url: Optional[str] = None,
    ):
        """Send notification for task completion."""
        duration_str = (
            f"{task_run.duration_seconds}s"
            if task_run.duration_seconds
            else "unknown"
        )

        message = (
            f"Task '{task_name}' completed successfully.\n\n"
            f"Duration: {duration_str}\n"
            f"{task_run.result_summary or ''}"
        )

        await self.send_notification(
            user_key=user_key,
            message=message,
            title=f"✅ CC-Docker: {task_name} Complete",
            priority=0,  # Normal priority
            url=discord_thread_url,
            url_title="View Results",
            task_run_id=task_run.id,
        )

    async def _log_notification(
        self,
        user_key: str,
        message: str,
        priority: int,
        pushover_response: dict,
        success: bool,
        task_run_id: Optional[str] = None,
    ):
        """Log notification to database."""
        notification = PushoverNotification(
            id=str(uuid4()),
            task_run_id=task_run_id,
            user_key=user_key,
            message=message,
            priority=priority,
            sent_at=datetime.now(timezone.utc),
            pushover_response=pushover_response,
            success=success,
        )

        self.db.add(notification)
        await self.db.commit()
