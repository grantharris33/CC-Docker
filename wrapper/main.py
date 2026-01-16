#!/usr/bin/env python3
"""Claude Code wrapper entry point."""

import asyncio
import logging
import signal
import sys
from typing import Optional

from claude_runner import InteractiveRunner
from config import WrapperConfig
from health import HealthReporter
from redis_publisher import RedisPublisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class WrapperApp:
    """Main wrapper application."""

    def __init__(self):
        self.config: Optional[WrapperConfig] = None
        self.publisher: Optional[RedisPublisher] = None
        self.runner: Optional[InteractiveRunner] = None
        self.health: Optional[HealthReporter] = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the wrapper application."""
        try:
            # Load configuration
            self.config = WrapperConfig.from_env()
            logger.info(f"Starting wrapper for session {self.config.session_id}")

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

    async def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up...")

        if self.runner:
            await self.runner.stop()

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
