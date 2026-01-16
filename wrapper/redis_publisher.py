"""Redis publisher for session output."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisPublisher:
    """Publishes Claude Code output to Redis pub/sub channels."""

    def __init__(self, redis_url: str, session_id: str):
        self.redis_url = redis_url
        self.session_id = session_id
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        self._client = redis.from_url(self.redis_url, decode_responses=True)
        logger.info(f"Connected to Redis at {self.redis_url}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def publish_output(self, message: Dict[str, Any]) -> None:
        """Publish output message to session channel."""
        if not self._client:
            raise RuntimeError("Not connected to Redis")

        payload = {
            "type": "output",
            "session_id": self.session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": message,
        }

        await self._client.publish(
            f"session:{self.session_id}:output",
            json.dumps(payload),
        )

    async def publish_result(
        self,
        result: str,
        subtype: str = "success",
        cost_usd: float = 0,
        usage: Optional[Dict] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """Publish final result to session channel."""
        if not self._client:
            raise RuntimeError("Not connected to Redis")

        payload = {
            "type": "result",
            "session_id": self.session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "subtype": subtype,
                "result": result,
                "total_cost_usd": cost_usd,
                "usage": usage or {},
                "duration_ms": duration_ms,
            },
        }

        await self._client.publish(
            f"session:{self.session_id}:output",
            json.dumps(payload),
        )

    async def publish_error(self, error: str) -> None:
        """Publish error message to session channel."""
        if not self._client:
            raise RuntimeError("Not connected to Redis")

        payload = {
            "type": "error",
            "session_id": self.session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"error": error},
        }

        await self._client.publish(
            f"session:{self.session_id}:output",
            json.dumps(payload),
        )

    async def update_state(self, status: str) -> None:
        """Update session state in Redis."""
        if not self._client:
            raise RuntimeError("Not connected to Redis")

        await self._client.hset(
            f"session:{self.session_id}:state",
            mapping={
                "status": status,
                "last_heartbeat": datetime.utcnow().isoformat(),
            },
        )

    async def get_input(self, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """Get input from session queue."""
        if not self._client:
            raise RuntimeError("Not connected to Redis")

        result = await self._client.blpop(
            f"session:{self.session_id}:input",
            timeout=timeout,
        )

        if result:
            return json.loads(result[1])
        return None

    async def subscribe_control(self):
        """Subscribe to control channel for session."""
        if not self._client:
            raise RuntimeError("Not connected to Redis")

        pubsub = self._client.pubsub()
        await pubsub.subscribe(f"session:{self.session_id}:control")
        return pubsub
