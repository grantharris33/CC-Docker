"""Redis pub/sub service for real-time communication."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, Optional

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PubSubService:
    """Service for Redis pub/sub operations."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._subscriptions: Dict[str, asyncio.Task] = {}

    async def publish(
        self, channel: str, message: Dict[str, Any]
    ) -> int:
        """Publish a message to a channel."""
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            **message,
        }
        return await self.redis.publish(channel, json.dumps(payload))

    async def publish_session_output(
        self, session_id: str, message: Dict[str, Any]
    ) -> int:
        """Publish output for a session."""
        return await self.publish(
            f"session:{session_id}:output",
            {"type": "output", "session_id": session_id, "data": message},
        )

    async def publish_session_result(
        self, session_id: str, result: Dict[str, Any]
    ) -> int:
        """Publish result for a session."""
        return await self.publish(
            f"session:{session_id}:output",
            {"type": "result", "session_id": session_id, "data": result},
        )

    async def publish_child_result(
        self, parent_session_id: str, child_session_id: str, result: Dict[str, Any]
    ) -> int:
        """Publish child session result to parent."""
        return await self.publish(
            f"session:{parent_session_id}:children",
            {
                "type": "child_result",
                "child_session_id": child_session_id,
                "data": result,
            },
        )

    async def subscribe(
        self, channel: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Subscribe to a channel and yield messages."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield data
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in message: {message['data']}")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def subscribe_session_output(
        self, session_id: str
    ) -> AsyncIterator[Dict[str, Any]]:
        """Subscribe to session output channel."""
        async for message in self.subscribe(f"session:{session_id}:output"):
            yield message

    async def subscribe_with_callback(
        self,
        channel: str,
        callback: Callable[[Dict[str, Any]], None],
    ) -> str:
        """Subscribe with a callback function."""
        subscription_id = f"{channel}:{id(callback)}"

        async def listener():
            async for message in self.subscribe(channel):
                try:
                    await callback(message)
                except Exception as e:
                    logger.error(f"Callback error for {channel}: {e}")

        task = asyncio.create_task(listener())
        self._subscriptions[subscription_id] = task
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from a channel."""
        if subscription_id in self._subscriptions:
            task = self._subscriptions.pop(subscription_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def push_input(self, session_id: str, prompt: str) -> None:
        """Push input to session's input queue."""
        await self.redis.rpush(
            f"session:{session_id}:input",
            json.dumps({"prompt": prompt, "timestamp": datetime.utcnow().isoformat()}),
        )

    async def pop_input(
        self, session_id: str, timeout: int = 0
    ) -> Optional[Dict[str, Any]]:
        """Pop input from session's input queue."""
        result = await self.redis.blpop(
            f"session:{session_id}:input", timeout=timeout
        )
        if result:
            return json.loads(result[1])
        return None

    async def send_control(
        self, session_id: str, command: str, data: Optional[Dict] = None
    ) -> int:
        """Send control message to session."""
        return await self.publish(
            f"session:{session_id}:control",
            {"command": command, "data": data or {}},
        )


async def get_pubsub_service(redis_client: redis.Redis) -> PubSubService:
    """Factory for PubSubService."""
    return PubSubService(redis_client)
