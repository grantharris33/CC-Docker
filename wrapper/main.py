#!/usr/bin/env python3
"""Claude Code wrapper entry point."""

import asyncio
import json
import logging
import signal
import sys
from typing import Optional

import redis.asyncio as redis

from claude_runner import InteractiveRunner
from config import WrapperConfig
from config_generator import ConfigGenerator
from health import HealthReporter
from redis_publisher import RedisPublisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class InterruptListener:
    """Listens for interrupt messages from parent sessions via Redis pub/sub."""

    def __init__(self, redis_url: str, session_id: str):
        self.redis_url = redis_url
        self.session_id = session_id
        self._client: Optional[redis.Redis] = None
        self._pubsub = None
        self._task: Optional[asyncio.Task] = None
        self._callbacks = []

    async def start(self) -> None:
        """Start listening for interrupts."""
        self._client = redis.from_url(self.redis_url)
        self._pubsub = self._client.pubsub()

        # Subscribe to interrupt channel
        await self._pubsub.subscribe(f"session:{self.session_id}:interrupt")

        # Start listener task
        self._task = asyncio.create_task(self._listen())
        logger.info(f"Interrupt listener started for session {self.session_id}")

        # Also check for any queued interrupts
        await self._process_queued_interrupts()

    async def stop(self) -> None:
        """Stop listening for interrupts."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()

        if self._client:
            await self._client.close()

    def on_interrupt(self, callback) -> None:
        """Register a callback for when an interrupt is received."""
        self._callbacks.append(callback)

    async def _listen(self) -> None:
        """Listen for interrupt messages."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        logger.info(f"Received interrupt: {data}")
                        await self._handle_interrupt(data)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid interrupt message: {message['data']}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Interrupt listener error: {e}")

    async def _process_queued_interrupts(self) -> None:
        """Process any interrupts that were queued before we started listening."""
        queue_key = f"session:{self.session_id}:interrupt_queue"
        while True:
            data = await self._client.lpop(queue_key)
            if not data:
                break
            try:
                interrupt = json.loads(data)
                logger.info(f"Processing queued interrupt: {interrupt}")
                await self._handle_interrupt(interrupt)
            except json.JSONDecodeError:
                logger.warning(f"Invalid queued interrupt: {data}")

    async def _handle_interrupt(self, data: dict) -> None:
        """Handle an interrupt message."""
        for callback in self._callbacks:
            try:
                await callback(data)
            except Exception as e:
                logger.error(f"Interrupt callback error: {e}")


class WrapperApp:
    """Main wrapper application."""

    def __init__(self):
        self.config: Optional[WrapperConfig] = None
        self.publisher: Optional[RedisPublisher] = None
        self.runner: Optional[InteractiveRunner] = None
        self.health: Optional[HealthReporter] = None
        self.interrupt_listener: Optional[InterruptListener] = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the wrapper application."""
        try:
            # Load configuration
            self.config = WrapperConfig.from_env()
            logger.info(f"Starting wrapper for session {self.config.session_id}")

            # Generate Claude Code configuration files
            self._generate_config_files()

            # Initialize Redis publisher
            self.publisher = RedisPublisher(
                self.config.redis_url,
                self.config.session_id,
            )
            await self.publisher.connect()

            # Start health reporter
            self.health = HealthReporter(
                self.config.redis_url,
                self.config.session_id,
            )
            await self.health.start()

            # Start interrupt listener (for parent -> child communication)
            self.interrupt_listener = InterruptListener(
                self.config.redis_url,
                self.config.session_id,
            )
            self.interrupt_listener.on_interrupt(self._handle_interrupt)
            await self.interrupt_listener.start()

            # Start interactive runner
            self.runner = InteractiveRunner(self.config, self.publisher)
            await self.runner.run()

        except Exception as e:
            logger.error(f"Fatal error: {e}")
            if self.publisher:
                await self.publisher.publish_error(str(e))
                await self.publisher.update_state("failed")
            raise
        finally:
            await self.cleanup()

    async def _handle_interrupt(self, data: dict) -> None:
        """Handle an interrupt message from parent or external source."""
        interrupt_type = data.get("type", "redirect")
        message = data.get("message", "")
        priority = data.get("priority", "normal")

        logger.info(f"Processing interrupt: type={interrupt_type}, priority={priority}")

        if interrupt_type == "stop":
            # Stop the session
            await self.shutdown()
        elif interrupt_type == "redirect":
            # Inject a new prompt to redirect the current work
            if message and self.runner:
                # Format the interrupt as a high-priority message
                interrupt_prompt = f"[INTERRUPT FROM PARENT - {priority.upper()} PRIORITY]\n\n{message}"
                await self.runner.inject_prompt(interrupt_prompt)
        elif interrupt_type == "pause":
            # Pause is not fully implemented yet, log and continue
            logger.warning("Pause interrupt not yet implemented")
        else:
            logger.warning(f"Unknown interrupt type: {interrupt_type}")

    async def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up...")

        if self.runner:
            await self.runner.stop()

        if self.interrupt_listener:
            await self.interrupt_listener.stop()

        if self.health:
            await self.health.stop()

        if self.publisher:
            await self.publisher.update_state("stopped")
            await self.publisher.close()

    async def shutdown(self) -> None:
        """Handle graceful shutdown."""
        logger.info("Shutdown requested")
        self._shutdown_event.set()
        if self.runner:
            await self.runner.stop()

    def _generate_config_files(self) -> None:
        """Generate Claude Code configuration files at startup."""
        try:
            # Extract MCP servers from claude_config if available
            mcp_servers = {}
            if self.config.claude_config and self.config.claude_config.mcp_servers:
                mcp_servers = self.config.claude_config.mcp_servers

            generator = ConfigGenerator(
                session_id=self.config.session_id,
                workspace_path=self.config.workspace_path,
                redis_url=self.config.redis_url,
                gateway_url=self.config.gateway_url,
                parent_session_id=self.config.parent_session_id,
                container_role="child" if self.config.parent_session_id else "root",
                mcp_servers=mcp_servers,
            )
            generator.generate_all()
            logger.info("Configuration files generated successfully")
        except Exception as e:
            logger.error(f"Failed to generate configuration files: {e}")
            # Don't fail startup - Claude Code can still work without these files
            pass


async def main() -> int:
    """Main entry point."""
    app = WrapperApp()

    # Set up signal handlers
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("Signal received, shutting down...")
        asyncio.create_task(app.shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await app.start()
        return 0
    except KeyboardInterrupt:
        logger.info("Interrupted")
        return 130
    except Exception as e:
        logger.error(f"Wrapper failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
