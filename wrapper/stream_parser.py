"""Parser for Claude Code JSON streaming output."""

import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

logger = logging.getLogger(__name__)


class StreamParser:
    """Parses Claude Code's stream-json output format."""

    def __init__(self):
        self.buffer = ""
        self.in_json = False
        self.brace_count = 0
        self.scan_position = 0  # Track how much we've already scanned

    def feed(self, data: str) -> list[Dict[str, Any]]:
        """
        Feed data to the parser and return any complete JSON objects.

        Args:
            data: Raw output data from Claude Code

        Returns:
            List of parsed JSON objects
        """
        results = []
        self.buffer += data

        while self.buffer:
            if not self.in_json:
                # Look for start of JSON object
                idx = self.buffer.find("{")
                if idx == -1:
                    self.buffer = ""
                    self.scan_position = 0
                    break
                self.buffer = self.buffer[idx:]
                self.in_json = True
                self.brace_count = 0
                self.scan_position = 0

            # Count braces to find complete JSON, starting from where we left off
            for i in range(self.scan_position, len(self.buffer)):
                char = self.buffer[i]
                if char == "{":
                    self.brace_count += 1
                elif char == "}":
                    self.brace_count -= 1

                    if self.brace_count == 0:
                        # Found complete JSON object
                        json_str = self.buffer[: i + 1]
                        self.buffer = self.buffer[i + 1 :]
                        self.in_json = False
                        self.scan_position = 0

                        try:
                            obj = json.loads(json_str)
                            results.append(obj)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse JSON: {e}")
                        break
            else:
                # Incomplete JSON, remember where we stopped
                self.scan_position = len(self.buffer)
                break

        return results

    def reset(self):
        """Reset parser state."""
        self.buffer = ""
        self.in_json = False
        self.brace_count = 0
        self.scan_position = 0


def extract_message_type(message: Dict[str, Any]) -> str:
    """
    Extract the type of a Claude Code message.

    Claude Code stream-json format includes various message types:
    - assistant: Text output from Claude
    - tool_use: Tool invocation
    - tool_result: Result of tool execution
    - result: Final result with cost/usage info
    - system: System messages
    """
    msg_type = message.get("type", "unknown")

    # Handle nested message structure
    if msg_type == "message":
        inner = message.get("message", {})
        return inner.get("type", "text")

    return msg_type


def format_for_client(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a Claude Code message for WebSocket client.

    Normalizes the message structure for consistent client handling.
    """
    msg_type = extract_message_type(message)

    if msg_type == "assistant":
        return {
            "type": "assistant",
            "message": message.get("message", {}),
        }

    elif msg_type == "tool_use":
        return {
            "type": "tool_use",
            "tool": message.get("tool", message.get("name")),
            "input": message.get("input", {}),
        }

    elif msg_type == "result":
        return {
            "type": "result",
            "subtype": message.get("subtype", "success"),
            "result": message.get("result"),
            "total_cost_usd": message.get("total_cost_usd", 0),
            "usage": message.get("usage", {}),
            "duration_ms": message.get("duration_ms"),
        }

    else:
        # Pass through other message types
        return message
