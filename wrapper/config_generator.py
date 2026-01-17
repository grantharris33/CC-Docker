"""Generate Claude Code configuration files at container startup."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigGenerator:
    """Generates Claude Code configuration files for CC-Docker containers."""

    def __init__(
        self,
        session_id: str,
        workspace_path: str = "/workspace",
        redis_url: str = "redis://redis:6379",
        gateway_url: str = "http://gateway:8000",
        parent_session_id: Optional[str] = None,
        container_role: str = "worker",
        mcp_servers: Optional[Dict[str, Any]] = None,
        secrets: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
    ):
        self.session_id = session_id
        self.workspace_path = workspace_path
        self.redis_url = redis_url
        self.gateway_url = gateway_url
        self.parent_session_id = parent_session_id
        self.container_role = container_role
        self.mcp_servers = mcp_servers or {}
        self.secrets = secrets or []
        self.skills = skills or ["delegate-task", "coordinate-children", "child-status"]

    def generate_all(self) -> None:
        """Generate all configuration files."""
        logger.info(f"Generating configuration files for session {self.session_id}")

        # Create directories
        self._create_directories()

        # Generate files
        self.generate_mcp_json()
        self.generate_settings_json()
        self.generate_claude_md()
        self.copy_skills()

        logger.info("Configuration files generated successfully")

    def _create_directories(self) -> None:
        """Create required directories."""
        dirs = [
            Path(self.workspace_path) / ".claude",
            Path(self.workspace_path) / ".claude" / "skills",
            Path("/home/claude/.claude"),
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created directory: {d}")

    def generate_mcp_json(self) -> str:
        """Generate /workspace/.mcp.json with MCP server configuration."""
        mcp_config = {
            "mcpServers": {
                # Always include CC-Docker MCP server for inter-session communication
                "cc-docker": {
                    "type": "stdio",
                    "command": "node",
                    "args": ["/opt/cc-docker-mcp/index.js"],
                    "env": {
                        "SESSION_ID": self.session_id,
                        "REDIS_URL": self.redis_url,
                        "GATEWAY_URL": self.gateway_url,
                    },
                },
                # Filesystem MCP server
                "filesystem": {
                    "type": "stdio",
                    "command": "npx",
                    "args": [
                        "-y",
                        "@modelcontextprotocol/server-filesystem",
                        "/workspace",
                        "/shared",
                    ],
                },
            }
        }

        # Add conditional MCP servers based on environment variables
        if os.environ.get("GITHUB_TOKEN"):
            mcp_config["mcpServers"]["github"] = {
                "type": "http",
                "url": "https://api.githubcopilot.com/mcp/",
                "headers": {
                    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                },
            }

        if os.environ.get("POSTGRES_URL"):
            mcp_config["mcpServers"]["postgres"] = {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@bytebase/dbhub"],
                "env": {
                    "DATABASE_URL": os.environ["POSTGRES_URL"],
                },
            }

        # Add Playwright MCP server
        mcp_config["mcpServers"]["playwright"] = {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@executeautomation/playwright-mcp-server", "--headless"],
            "env": {
                "PLAYWRIGHT_BROWSERS_PATH": "/opt/playwright-browsers",
            },
        }

        # Add SQLite MCP server
        mcp_config["mcpServers"]["sqlite"] = {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@executeautomation/sqlite-mcp-server"],
            "env": {
                "SQLITE_DB_PATH": os.environ.get("SQLITE_DB_PATH", "/workspace/data.db"),
            },
        }

        # Merge with any custom MCP servers from session config
        for name, config in self.mcp_servers.items():
            mcp_config["mcpServers"][name] = config

        mcp_path = Path(self.workspace_path) / ".mcp.json"
        with open(mcp_path, "w") as f:
            json.dump(mcp_config, f, indent=2)

        logger.info(f"Generated {mcp_path}")
        return str(mcp_path)

    def generate_settings_json(self) -> str:
        """Generate /home/claude/.claude/settings.json with permissions."""
        settings = {
            "permissions": {
                "allow": [
                    "Bash(*)",
                    "Read(*)",
                    "Write(*)",
                    "Edit(*)",
                    "Glob(*)",
                    "Grep(*)",
                    "WebFetch(*)",
                    "Task(*)",
                    "mcp__cc-docker__*",
                    "mcp__filesystem__*",
                    "mcp__playwright__*",
                    "mcp__sqlite__*",
                ],
                "deny": [],
                "defaultMode": "bypassPermissions",
            },
            "env": {
                "SESSION_ID": self.session_id,
                "REDIS_URL": self.redis_url,
                "GATEWAY_URL": self.gateway_url,
                "MCP_TIMEOUT": "30000",
                "MAX_MCP_OUTPUT_TOKENS": "50000",
            },
        }

        if self.parent_session_id:
            settings["env"]["PARENT_SESSION_ID"] = self.parent_session_id

        # Add GitHub/Postgres permissions if available
        if os.environ.get("GITHUB_TOKEN"):
            settings["permissions"]["allow"].append("mcp__github__*")

        if os.environ.get("POSTGRES_URL"):
            settings["permissions"]["allow"].append("mcp__postgres__*")

        settings_path = Path("/home/claude/.claude/settings.json")
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)

        logger.info(f"Generated {settings_path}")
        return str(settings_path)

    def generate_claude_md(self) -> str:
        """Generate /workspace/.claude/CLAUDE.md with session context."""
        parent_info = (
            f'- **Parent Session**: {self.parent_session_id}'
            if self.parent_session_id
            else '- **Parent Session**: None (root session)'
        )

        content = f"""# CC-Docker Session Context

## Session Information
- **Session ID**: {self.session_id}
{parent_info}
- **Container Role**: {self.container_role}

## Available Capabilities

### MCP Servers
- **cc-docker**: Inter-session communication (spawn_child, send_to_child, get_child_output, get_child_result, list_children, stop_child)
- **filesystem**: Enhanced file operations in /workspace and /shared
- **playwright**: Headless browser automation for web scraping and testing
- **sqlite**: Local SQLite database operations
"""

        # Add conditional servers
        if os.environ.get("GITHUB_TOKEN"):
            content += "- **github**: GitHub repository management, PRs, issues\n"

        if os.environ.get("POSTGRES_URL"):
            content += "- **postgres**: PostgreSQL database queries and schema management\n"

        content += """
### Skills (Slash Commands)
- **/delegate-task**: Delegate work to a child Docker container session
- **/coordinate-children**: Manage multiple parallel child sessions
- **/child-status**: Monitor child session status

## Guidelines

### When to Use Docker Children (spawn_child)
- Task needs isolation (separate workspace, fresh context)
- Task is long-running (>30 seconds)
- Task can run in parallel with other work
- Task involves heavy computation or many file operations
- Multi-file refactoring, parallel code review, research tasks

### When to Use Built-in Task Tool Instead
- Quick code exploration or file search
- Simple questions that need codebase context
- Tasks that benefit from shared parent context

## Best Practices
- Break large tasks into smaller, focused subtasks
- Each child should have a single, clear objective
- Provide enough context but avoid overwhelming the child
- Use streaming for long-running tasks to monitor progress
- Always check child results before proceeding
- Clean up completed children to free resources

## Resource Limits
- Maximum concurrent children: 5 (configurable)
- Maximum child depth: 3 (prevent infinite recursion)
- Child timeout: 30 minutes (configurable)
"""

        claude_md_path = Path(self.workspace_path) / ".claude" / "CLAUDE.md"
        with open(claude_md_path, "w") as f:
            f.write(content)

        logger.info(f"Generated {claude_md_path}")
        return str(claude_md_path)

    def copy_skills(self) -> None:
        """Copy skills from /opt/cc-docker/skills to /workspace/.claude/skills."""
        source_dir = Path("/opt/cc-docker/skills")
        dest_dir = Path(self.workspace_path) / ".claude" / "skills"

        if not source_dir.exists():
            logger.warning(f"Skills source directory not found: {source_dir}")
            # Create embedded skills if source doesn't exist
            self._create_embedded_skills(dest_dir)
            return

        # Copy each skill directory
        import shutil

        for skill_dir in source_dir.iterdir():
            if skill_dir.is_dir():
                dest_skill_dir = dest_dir / skill_dir.name
                if dest_skill_dir.exists():
                    shutil.rmtree(dest_skill_dir)
                shutil.copytree(skill_dir, dest_skill_dir)
                logger.debug(f"Copied skill: {skill_dir.name}")

        logger.info(f"Copied skills to {dest_dir}")

    def _create_embedded_skills(self, dest_dir: Path) -> None:
        """Create embedded skill definitions if source directory doesn't exist."""
        skills = {
            "delegate-task": self._get_delegate_task_skill(),
            "coordinate-children": self._get_coordinate_children_skill(),
            "child-status": self._get_child_status_skill(),
        }

        for skill_name, content in skills.items():
            skill_dir = dest_dir / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_file = skill_dir / "SKILL.md"
            with open(skill_file, "w") as f:
                f.write(content)
            logger.debug(f"Created embedded skill: {skill_name}")

        logger.info(f"Created embedded skills in {dest_dir}")

    def _get_delegate_task_skill(self) -> str:
        """Return the delegate-task skill content."""
        return '''---
name: delegate-task
description: |
  Delegate a task to a child Docker container session. Use when you need to:
  - Parallelize work across multiple isolated instances
  - Isolate a complex subtask that needs its own context
  - Run long-running operations without blocking
  - Process multiple files/directories concurrently
  Keywords: spawn, child, parallel, delegate, fork, worker
allowed-tools:
  - mcp__cc-docker__spawn_child
  - mcp__cc-docker__get_child_output
  - mcp__cc-docker__get_child_result
  - mcp__cc-docker__list_children
  - Read
  - Write
user-invocable: true
---

# Delegate Task

When delegating a task to a child Docker container session:

## Decision Criteria

**Use Docker child (this skill)** when:
- Task needs isolation (separate workspace, fresh context)
- Task is long-running (>30 seconds)
- Task can run in parallel with other work
- Task involves heavy computation or many file operations

**Use built-in Task tool instead** when:
- Quick code exploration or file search
- Simple questions that need codebase context
- Tasks that benefit from shared parent context

## Usage

Use the CC-Docker MCP `spawn_child` tool:

```
spawn_child(
  prompt="Your detailed task description",
  context={"key": "value"},  # Optional context data
  stream_output=true          # Whether to stream output back
)
```

## Best Practices

- Break large tasks into smaller, focused subtasks
- Each child should have a single, clear objective
- Provide enough context but avoid overwhelming the child
- Use streaming for long-running tasks to monitor progress
- Always check child results before proceeding
- Clean up completed children to free resources
'''

    def _get_coordinate_children_skill(self) -> str:
        """Return the coordinate-children skill content."""
        return '''---
name: coordinate-children
description: |
  Coordinate multiple Docker container child sessions working on related tasks.
  Use when parallelizing work across multiple children or when tasks have dependencies.
  Keywords: parallel, concurrent, fan-out, fan-in, pipeline, orchestrate, coordinate
allowed-tools:
  - mcp__cc-docker__spawn_child
  - mcp__cc-docker__send_to_child
  - mcp__cc-docker__get_child_output
  - mcp__cc-docker__get_child_result
  - mcp__cc-docker__list_children
  - mcp__cc-docker__stop_child
  - Read
  - Write
user-invocable: true
---

# Coordinate Children

When coordinating multiple Docker container child sessions:

## Workflow

1. **Plan the work breakdown**: Identify tasks that can run in parallel
2. **Spawn children**: Create child sessions for each parallel task
3. **Monitor progress**: Track status of all children via streaming
4. **Aggregate results**: Combine results once all children complete
5. **Handle failures**: Decide how to proceed if a child fails
6. **Cleanup**: Stop any remaining children

## Patterns

### Fan-out / Fan-in
Spawn multiple children for parallel work, then aggregate:

```
# Spawn children for each file
children = []
for file in files:
    child = spawn_child(prompt=f"Analyze {file}")
    children.append(child)

# Wait for all and aggregate
results = [get_child_result(c, wait=true) for c in children]
aggregate_results(results)
```

### Pipeline
Chain children where one's output feeds the next:

```
# Stage 1: Analysis
analysis = spawn_child(prompt="Analyze the codebase")
result1 = get_child_result(analysis, wait=true)

# Stage 2: Use analysis results
implementation = spawn_child(prompt=f"Implement based on: {result1}")
result2 = get_child_result(implementation, wait=true)
```

## Resource Limits

- Maximum concurrent children: 5 (configurable)
- Maximum child depth: 3 (prevent infinite recursion)
- Child timeout: 30 minutes (configurable)
'''

    def _get_child_status_skill(self) -> str:
        """Return the child-status skill content."""
        return '''---
name: child-status
description: |
  Check the status of Docker container child sessions. Use when you need to:
  - Monitor progress of running children
  - Check if children are complete
  - Debug stuck or failed sessions
  - View streaming output
  Keywords: status, monitor, progress, children, check, debug
allowed-tools:
  - mcp__cc-docker__list_children
  - mcp__cc-docker__get_child_output
  - mcp__cc-docker__get_child_result
  - mcp__cc-docker__stop_child
user-invocable: true
---

# Child Session Status

## Quick Commands

- `list_children()` - Show all your child sessions
- `get_child_output(id)` - Get latest output from a child
- `get_child_result(id, wait=false)` - Check if result is ready
- `stop_child(id)` - Terminate a child session

## Status Values

| Status | Meaning |
|--------|---------|
| `starting` | Container is being created |
| `idle` | Ready for input |
| `running` | Processing a prompt |
| `stopped` | Cleanly terminated |
| `failed` | Error occurred |

## Troubleshooting

**Child stuck in "running"**:
- Check streaming output with `get_child_output(id)`
- Consider sending follow-up prompt with `send_to_child(id, prompt)`
- As last resort, use `stop_child(id, force=true)`

**Child failed**:
- Check error details in `get_child_result(id)`
- Review container logs if available
- Spawn a new child with adjusted prompt/config
'''
