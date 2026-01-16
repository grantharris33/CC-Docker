"""Claude Code configuration models for plugins, MCPs, and skills."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server."""

    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)

    # For HTTP/SSE servers
    type: Optional[str] = None  # "http", "sse", "stdio"
    url: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)


class PluginConfig(BaseModel):
    """Configuration for a Claude Code plugin."""

    name: str
    path: Optional[str] = None  # Path to plugin directory
    enabled: bool = True
    settings: Dict[str, Any] = Field(default_factory=dict)


class ClaudeCodeConfig(BaseModel):
    """Complete Claude Code configuration for a session."""

    # MCP servers
    mcp_servers: Dict[str, MCPServerConfig] = Field(
        default_factory=dict,
        description="MCP server configurations keyed by server name"
    )

    # Plugins
    plugins: List[PluginConfig] = Field(
        default_factory=list,
        description="Plugin configurations to load"
    )

    plugin_dirs: List[str] = Field(
        default_factory=list,
        description="Additional plugin directories to load"
    )

    # Skills (slash commands)
    skills_enabled: bool = Field(
        default=True,
        description="Whether to enable skills/slash commands"
    )

    disabled_skills: List[str] = Field(
        default_factory=list,
        description="Skills to disable (e.g., ['commit', 'review'])"
    )

    # Model settings
    model: Optional[str] = Field(
        default=None,
        description="Model to use (e.g., 'opus', 'sonnet')"
    )

    # Tools
    allowed_tools: List[str] = Field(
        default_factory=lambda: ["*"],
        description="Tools to allow (* for all, or list specific tools)"
    )

    disallowed_tools: List[str] = Field(
        default_factory=list,
        description="Tools to disallow"
    )

    # System prompt
    system_prompt: Optional[str] = Field(
        default=None,
        description="Custom system prompt"
    )

    append_system_prompt: Optional[str] = Field(
        default=None,
        description="Text to append to default system prompt"
    )

    # Agents
    custom_agents: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Custom agent definitions"
    )

    # Additional settings
    verbose: bool = Field(
        default=False,
        description="Enable verbose output"
    )

    permission_mode: str = Field(
        default="bypassPermissions",
        description="Permission mode (bypassPermissions, default, plan, etc.)"
    )

    def to_claude_args(self) -> List[str]:
        """Convert configuration to Claude Code CLI arguments."""
        args = []

        # MCP servers
        if self.mcp_servers:
            import json
            mcp_config = {"mcpServers": {
                name: {k: v for k, v in server.model_dump().items() if v}
                for name, server in self.mcp_servers.items()
            }}
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
            import json
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


class SessionClaudeConfig(BaseModel):
    """Configuration passed when creating a session."""

    allowed_tools: List[str] = Field(default_factory=lambda: ["*"])
    max_turns: int = 100
    timeout_seconds: int = 3600

    # Claude Code specific configuration
    claude_config: Optional[ClaudeCodeConfig] = None
