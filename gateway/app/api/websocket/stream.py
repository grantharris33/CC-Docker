"""WebSocket streaming for real-time Claude Code output."""

import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as redis
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_db, get_redis
from app.core.security import decode_token
from app.db.models import Session
from app.models.message import WSMessageType
from app.models.session import SessionStatus
from app.services.pubsub import PubSubService, get_pubsub_service

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections for sessions."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info(f"WebSocket connected for session {session_id}")

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info(f"WebSocket disconnected for session {session_id}")

    async def broadcast(self, session_id: str, message: dict) -> None:
        """Broadcast a message to all connections for a session."""
        if session_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)

            for conn in disconnected:
                self.disconnect(session_id, conn)


manager = ConnectionManager()


async def authenticate_websocket(websocket: WebSocket) -> Optional[str]:
    """Authenticate WebSocket connection from query params or first message."""
    # Try token from query params
    token = websocket.query_params.get("token")
    if token:
        try:
            payload = decode_token(token)
            return payload.sub
        except Exception:
            pass

    # Try Sec-WebSocket-Protocol header
    protocol = websocket.headers.get("sec-websocket-protocol")
    if protocol:
        try:
            payload = decode_token(protocol)
            return payload.sub
        except Exception:
            pass

    return None


@router.websocket("/{session_id}/stream")
async def websocket_stream(
    websocket: WebSocket,
    session_id: str,
):
    """
    WebSocket endpoint for streaming Claude Code output.

    Connect to receive real-time output from a Claude Code session.
    Send prompts through this connection to continue the conversation.

    Client -> Server messages:
    - {"type": "prompt", "prompt": "..."}
    - {"type": "ping"}

    Server -> Client messages:
    - {"type": "assistant", "message": {...}}
    - {"type": "tool_use", "tool": "...", "input": {...}}
    - {"type": "result", "subtype": "success", "result": "...", ...}
    - {"type": "system", "event": "...", "data": {...}}
    - {"type": "pong"}
    """
    # Authenticate
    user_id = await authenticate_websocket(websocket)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Connect Redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)

    try:
        # Verify session exists
        async with get_db_session() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()

            if not session:
                await websocket.close(code=4004, reason="Session not found")
                return

        await manager.connect(session_id, websocket)

        # Send session started event
        await websocket.send_json(
            {
                "type": WSMessageType.SYSTEM,
                "event": "session_connected",
                "data": {"session_id": session_id},
            }
        )

        # Create pubsub service
        pubsub = PubSubService(redis_client)

        # Start tasks for receiving messages and forwarding output
        receive_task = asyncio.create_task(
            handle_client_messages(websocket, session_id, pubsub)
        )
        forward_task = asyncio.create_task(
            forward_session_output(websocket, session_id, pubsub)
        )

        # Wait for either task to complete
        done, pending = await asyncio.wait(
            [receive_task, forward_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        try:
            await websocket.send_json(
                {
                    "type": WSMessageType.ERROR,
                    "data": {"error": str(e)},
                }
            )
        except Exception:
            pass
    finally:
        manager.disconnect(session_id, websocket)
        await redis_client.aclose()


async def handle_client_messages(
    websocket: WebSocket,
    session_id: str,
    pubsub: PubSubService,
) -> None:
    """Handle incoming messages from WebSocket client."""
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "prompt":
                prompt = data.get("prompt")
                if prompt:
                    await pubsub.push_input(session_id, prompt)
                    logger.info(f"Received prompt for session {session_id}")

    except WebSocketDisconnect:
        raise
    except Exception as e:
        logger.error(f"Error handling client message: {e}")
        raise


async def forward_session_output(
    websocket: WebSocket,
    session_id: str,
    pubsub: PubSubService,
) -> None:
    """Forward session output to WebSocket client."""
    try:
        async for message in pubsub.subscribe_session_output(session_id):
            msg_type = message.get("type")
            data = message.get("data", {})

            if msg_type == "output":
                # Forward Claude Code output directly
                await websocket.send_json(data)

            elif msg_type == "result":
                # Send result message
                await websocket.send_json(
                    {
                        "type": WSMessageType.RESULT,
                        "subtype": data.get("subtype", "success"),
                        "result": data.get("result"),
                        "total_cost_usd": data.get("total_cost_usd"),
                        "usage": data.get("usage"),
                    }
                )

            elif msg_type == "child_result":
                # Forward child session result
                await websocket.send_json(
                    {
                        "type": WSMessageType.CHILD_RESULT,
                        "child_session_id": message.get("child_session_id"),
                        "result": data,
                    }
                )

            elif msg_type == "error":
                await websocket.send_json(
                    {
                        "type": WSMessageType.ERROR,
                        "data": data,
                    }
                )

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error forwarding output: {e}")
        raise


async def get_db_session():
    """Get database session context manager."""
    from app.db.database import get_db_context

    return get_db_context()
