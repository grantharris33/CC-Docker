"""WebSocket proxy for VNC access to container desktops."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import decode_token
from app.db.database import get_db_context
from app.db.models import Session
from app.services.container import container_manager

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


async def authenticate_websocket(websocket: WebSocket) -> Optional[str]:
    """Authenticate WebSocket connection from query params or headers."""
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


@router.websocket("/{session_id}/vnc")
async def websocket_vnc_proxy(
    websocket: WebSocket,
    session_id: str,
):
    """
    WebSocket proxy for VNC access to container desktop.

    This endpoint provides noVNC-compatible WebSocket access to the
    container's VNC server running on port 5900.

    Usage:
    - Connect noVNC client to: ws://gateway/api/v1/sessions/{session_id}/vnc?token={jwt}
    - VNC traffic is proxied bidirectionally to container's port 5900
    """
    # Authenticate
    user_id = await authenticate_websocket(websocket)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    try:
        # Verify session exists and get container info
        async with get_db_context() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()

            if not session:
                await websocket.close(code=4004, reason="Session not found")
                return

            if not session.container_id:
                await websocket.close(code=4003, reason="Session has no container")
                return

        # Get container network info
        container_info = await container_manager.get_container_info(session.container_id)
        if not container_info:
            await websocket.close(code=4004, reason="Container not found")
            return

        # Get container IP address (assumes container is on cc-internal network)
        networks = container_info.get("NetworkSettings", {}).get("Networks", {})
        container_ip = None
        for network_name, network_config in networks.items():
            if "cc-internal" in network_name:
                container_ip = network_config.get("IPAddress")
                break

        if not container_ip:
            await websocket.close(code=4003, reason="Container not on network")
            return

        vnc_host = container_ip
        vnc_port = 5900

        logger.info(f"Connecting VNC proxy for session {session_id} to {vnc_host}:{vnc_port}")

        # Accept WebSocket connection
        await websocket.accept()

        # Connect to VNC server
        vnc_reader, vnc_writer = await asyncio.open_connection(vnc_host, vnc_port)

        # Start bidirectional proxy tasks
        ws_to_vnc_task = asyncio.create_task(
            proxy_websocket_to_vnc(websocket, vnc_writer)
        )
        vnc_to_ws_task = asyncio.create_task(
            proxy_vnc_to_websocket(vnc_reader, websocket)
        )

        # Wait for either task to complete
        done, pending = await asyncio.wait(
            [ws_to_vnc_task, vnc_to_ws_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Close VNC connection
        vnc_writer.close()
        await vnc_writer.wait_closed()

        logger.info(f"VNC proxy closed for session {session_id}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for VNC session {session_id}")
    except Exception as e:
        logger.error(f"VNC proxy error for session {session_id}: {e}")
        try:
            await websocket.close(code=1011, reason=f"Proxy error: {str(e)}")
        except Exception:
            pass


async def proxy_websocket_to_vnc(websocket: WebSocket, vnc_writer) -> None:
    """Forward data from WebSocket client to VNC server."""
    try:
        while True:
            # Receive binary data from WebSocket
            data = await websocket.receive_bytes()

            # Forward to VNC server
            vnc_writer.write(data)
            await vnc_writer.drain()

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected in ws->vnc proxy")
        raise
    except Exception as e:
        logger.error(f"Error in ws->vnc proxy: {e}")
        raise


async def proxy_vnc_to_websocket(vnc_reader, websocket: WebSocket) -> None:
    """Forward data from VNC server to WebSocket client."""
    try:
        while True:
            # Read from VNC server (up to 64KB at a time)
            data = await vnc_reader.read(65536)

            if not data:
                # VNC connection closed
                break

            # Forward to WebSocket client
            await websocket.send_bytes(data)

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected in vnc->ws proxy")
        raise
    except Exception as e:
        logger.error(f"Error in vnc->ws proxy: {e}")
        raise
