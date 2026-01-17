"""Claude Code process management."""

import asyncio
import logging
import os
import signal
import time
from typing import Any, Dict, Optional

from config import WrapperConfig
from redis_publisher import RedisPublisher
from stream_parser import StreamParser, format_for_client

logger = logging.getLogger(__name__)


class ClaudeRunner:
    """Manages the Claude Code process."""

    def __init__(self, config: WrapperConfig, publisher: RedisPublisher):
        self.config = config
        self.publisher = publisher
        self.parser = StreamParser()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._running = False
        self._claude_session_id: Optional[str] = None  # Claude's internal session ID for resume

    async def run_prompt(self, prompt: str, resume: bool = False) -> Dict[str, Any]:
        """
        Run Claude Code with the given prompt.

        Args:
            prompt: The prompt to send to Claude Code
            resume: Whether to resume an existing session

        Returns:
            The final result from Claude Code
        """
        start_time = time.time()
        self._running = True

        # Build command
        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "stream-json",
            "--verbose",  # Required for stream-json with -p
        ]

        # Add configuration from claude_config if available
        if self.config.claude_config:
            cmd.extend(self.config.claude_config.to_claude_args())
        else:
            # Default: bypass permissions
            cmd.append("--dangerously-skip-permissions")

        if resume and self._claude_session_id:
            cmd.extend(["--resume", self._claude_session_id])

        logger.info(f"Running Claude Code: {' '.join(cmd[:6])}...")

        # Start process
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.config.workspace_path,
            env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "cc-docker"},
        )

        result = None
        usage = {"input_tokens": 0, "output_tokens": 0}

        try:
            # Stream output
            async for message in self._stream_output():
                msg_type = message.get("type")

                # Don't forward result messages - they're sent via publish_result()
                if msg_type != "result":
                    formatted = format_for_client(message)
                    await self.publisher.publish_output(formatted)

                # Track result
                if msg_type == "result":
                    result = message.get("result", "")
                    raw_usage = message.get("usage", {})
                    usage = {
                        "input_tokens": raw_usage.get("input_tokens", raw_usage.get("inputTokens", 0)),
                        "output_tokens": raw_usage.get("output_tokens", raw_usage.get("outputTokens", 0)),
                    }
                    # Capture Claude's session ID for multi-turn resume
                    if message.get("session_id"):
                        self._claude_session_id = message["session_id"]
                        logger.debug(f"Captured Claude session ID: {self._claude_session_id}")

            # Wait for process to complete
            await self._process.wait()

        except asyncio.CancelledError:
            await self.stop()
            raise
        finally:
            self._running = False

        duration_ms = int((time.time() - start_time) * 1000)

        # Publish final result
        await self.publisher.publish_result(
            result=result or "",
            subtype="success" if self._process.returncode == 0 else "error",
            usage=usage,
            duration_ms=duration_ms,
        )

        return {
            "result": result,
            "usage": usage,
            "duration_ms": duration_ms,
            "exit_code": self._process.returncode,
        }

    async def _stream_output(self):
        """Stream and parse Claude Code output."""
        if not self._process or not self._process.stdout:
            logger.warning("No process or stdout available")
            return

        self.parser.reset()
        total_bytes = 0

        while True:
            chunk = await self._process.stdout.read(4096)
            if not chunk:
                logger.debug(f"Stream ended after {total_bytes} bytes")
                break

            total_bytes += len(chunk)
            # Parse JSON objects from stream
            data = chunk.decode("utf-8", errors="replace")
            logger.debug(f"Received chunk ({len(chunk)} bytes): {data[:100]}...")
            messages = self.parser.feed(data)

            for message in messages:
                logger.info(f"Parsed message type: {message.get('type')}")
                yield message

    async def stop(self) -> None:
        """Stop the Claude Code process."""
        if self._process and self._running:
            logger.info("Stopping Claude Code process...")
            try:
                self._process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass
            self._running = False

    @property
    def is_running(self) -> bool:
        """Check if Claude Code is running."""
        return self._running


class InteractiveRunner:
    """Manages interactive Claude Code sessions with multi-turn support."""

    def __init__(self, config: WrapperConfig, publisher: RedisPublisher):
        self.config = config
        self.publisher = publisher
        self.runner = ClaudeRunner(config, publisher)
        self._turn_count = 0
        self._shutdown = False

    async def run(self) -> None:
        """Run the interactive session loop."""
        logger.info(f"Starting interactive session {self.config.session_id}")

        await self.publisher.update_state("idle")

        while not self._shutdown:
            try:
                # Wait for input
                input_data = await self.publisher.get_input(timeout=1)

                if input_data is None:
                    continue

                prompt = input_data.get("prompt")
                if not prompt:
                    continue

                logger.info(f"Received prompt (turn {self._turn_count + 1})")

                # Update state
                await self.publisher.update_state("running")

                # Run Claude Code
                resume = self._turn_count > 0
                result = await self.runner.run_prompt(prompt, resume=resume)

                self._turn_count += 1

                # Update state
                await self.publisher.update_state("idle")

            except asyncio.CancelledError:
                logger.info("Session cancelled")
                break
            except Exception as e:
                logger.error(f"Error in session loop: {e}")
                await self.publisher.publish_error(str(e))
                await self.publisher.update_state("idle")

        logger.info(f"Session {self.config.session_id} ended after {self._turn_count} turns")

    async def stop(self) -> None:
        """Stop the interactive session."""
        self._shutdown = True
        await self.runner.stop()

    async def inject_prompt(self, prompt: str) -> None:
        """Inject a prompt into the session queue.

        This allows external sources (like parent session interrupts) to
        send messages that will be processed after the current turn completes.
        """
        logger.info(f"Injecting prompt into session queue: {prompt[:50]}...")
        await self.publisher.inject_input({"prompt": prompt})
