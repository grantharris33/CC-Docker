"""Wrapper configuration."""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClaudeConfig:
    """Claude Code configuration for plugins, MCPs, and skills."""

    mcp_servers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    plugin_dirs: List[str] = field(default_factory=list)
    model: Optional[str] = None
    allowed_tools: List[str] = field(default_factory=lambda: ["*"])
    disallowed_tools: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    append_system_prompt: Optional[str] = None
    custom_agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    skills_enabled: bool = True
    verbose: bool = False
    permission_mode: str = "bypassPermissions"

    def to_claude_args(self) -> List[str]:
        """Convert configuration to Claude Code CLI arguments."""
        args = []

        # MCP servers
        if self.mcp_servers:
            mcp_config = {"mcpServers": self.mcp_servers}
            args.extend(["--mcp-config", json.dumps(mcp_config)])

        # Plugin directories
        for plugin_dir in self.plugin_dirs:
            args.extend(["--plugin-dir", plugin_dir])

        # Model
        if self.model:
            args.extend(["--model", self.model])

        # Tools
        if self.allowed_tools and self.allowed_tools != ["*"]:
            args.extend(["--allowed-tools", ",".join(self.allowed_tools)])

        if self.disallowed_tools:
            args.extend(["--disallowed-tools", ",".join(self.disallowed_tools)])

        # System prompt
        if self.system_prompt:
            args.extend(["--system-prompt", self.system_prompt])

        if self.append_system_prompt:
            args.extend(["--append-system-prompt", self.append_system_prompt])

        # Agents
        if self.custom_agents:
            args.extend(["--agents", json.dumps(self.custom_agents)])

        # Skills
        if not self.skills_enabled:
            args.append("--disable-slash-commands")

        # Permission mode
        if self.permission_mode == "bypassPermissions":
            args.append("--dangerously-skip-permissions")
        else:
            args.extend(["--permission-mode", self.permission_mode])

        # Verbose
        if self.verbose:
            args.append("--verbose")

        return args

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClaudeConfig":
        """Create config from dictionary."""
        return cls(
            mcp_servers=data.get("mcp_servers", {}),
            plugin_dirs=data.get("plugin_dirs", []),
            model=data.get("model"),
            allowed_tools=data.get("allowed_tools", ["*"]),
            disallowed_tools=data.get("disallowed_tools", []),
            system_prompt=data.get("system_prompt"),
            append_system_prompt=data.get("append_system_prompt"),
            custom_agents=data.get("custom_agents", {}),
            skills_enabled=data.get("skills_enabled", True),
            verbose=data.get("verbose", False),
            permission_mode=data.get("permission_mode", "bypassPermissions"),
        )


@dataclass
class WrapperConfig:
    """Configuration for the Claude Code wrapper."""

    session_id: str
    redis_url: str
    gateway_url: str
    parent_session_id: Optional[str] = None
    workspace_path: str = "/workspace"
    claude_model: str = "opus-4"
    claude_config: Optional[ClaudeConfig] = None

    @classmethod
    def from_env(cls) -> "WrapperConfig":
        """Create config from environment variables."""
        session_id = os.environ.get("SESSION_ID")
        if not session_id:
            raise ValueError("SESSION_ID environment variable is required")

        # Parse Claude config from environment
        claude_config = None
        claude_config_json = os.environ.get("CLAUDE_CONFIG")
        if claude_config_json:
            try:
                config_data = json.loads(claude_config_json)
                claude_config = ClaudeConfig.from_dict(config_data)
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse CLAUDE_CONFIG: {e}")

        return cls(
            session_id=session_id,
            redis_url=os.environ.get("REDIS_URL", "redis://redis:6379"),
            gateway_url=os.environ.get("GATEWAY_URL", "http://gateway:8000"),
            parent_session_id=os.environ.get("PARENT_SESSION_ID"),
            workspace_path=os.environ.get("WORKSPACE_PATH", "/workspace"),
            claude_model=os.environ.get("CLAUDE_MODEL", "opus-4"),
            claude_config=claude_config,
        )
