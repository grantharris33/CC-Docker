"""Health reporting for the wrapper."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class HealthReporter:
    """Reports health status to Redis."""

    def __init__(
        self,
        redis_url: str,
        session_id: str,
        interval: int = 10,
    ):
        self.redis_url = redis_url
        self.session_id = session_id
        self.interval = interval
        self._client: Optional[redis.Redis] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the health reporter."""
        self._client = redis.from_url(self.redis_url, decode_responses=True)
        self._running = True
        self._task = asyncio.create_task(self._report_loop())
        logger.info("Health reporter started")

    async def stop(self) -> None:
        """Stop the health reporter."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        logger.info("Health reporter stopped")

    async def _report_loop(self) -> None:
        """Periodically report health status."""
        while self._running:
            try:
                await self._report()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reporting health: {e}")
                await asyncio.sleep(self.interval)

    async def _report(self) -> None:
        """Report current health status."""
        if not self._client:
            return

        await self._client.hset(
            f"session:{self.session_id}:state",
            "last_heartbeat",
            datetime.utcnow().isoformat(),
        )

        # Set expiry on state key (if no heartbeat in 60s, consider dead)
        await self._client.expire(f"session:{self.session_id}:state", 60)
