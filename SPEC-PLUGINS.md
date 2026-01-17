# CC-Docker Plugins, MCPs, and Inter-Session Communication Specification

## Overview

This specification defines the plugin architecture, MCP (Model Context Protocol) server integration, and inter-session communication capabilities for CC-Docker. The goal is to enable Claude Code instances running in containers to:

1. **Spawn and interact with child sessions** using a hybrid approach (Docker containers for heavy/isolated tasks, built-in subagents for quick tasks)
2. **Access external services** via pre-installed MCP servers (GitHub, databases, filesystem, browser automation)
3. **Leverage custom skills** designed for multi-agent orchestration
4. **Perform browser automation** via headless Playwright
5. **Securely access credentials** via environment variables

### Design Philosophy

CC-Docker provides a cost-effective SDK/API layer on top of Claude Code CLI subscriptions. By running Claude Code CLI in isolated Docker containers and exposing a REST/WebSocket API, organizations can leverage subscription-based pricing ($20/month) for high-volume workloads instead of per-token API pricing.

**Key Constraints:**
- Claude Code CLI is the execution engine (not direct API calls)
- Configuration must align with Claude Code's expected file locations and formats
- Container isolation provides security but requires careful state management

---

## Table of Contents

1. [Claude Code Configuration Alignment](#1-claude-code-configuration-alignment)
2. [Inter-Session Communication](#2-inter-session-communication)
   - 2.7 [Discord Integration (Human-in-the-Loop)](#27-discord-integration-human-in-the-loop)
3. [Pre-installed MCP Servers](#3-pre-installed-mcp-servers)
4. [Custom CC-Docker Skills](#4-custom-cc-docker-skills)
5. [Browser Automation](#5-browser-automation)
6. [Secrets Management](#6-secrets-management)
7. [Container Architecture](#7-container-architecture)
8. [Configuration](#8-configuration)
9. [Security Considerations](#9-security-considerations)
10. [Implementation Phases](#10-implementation-phases)

---

## 1. Claude Code Configuration Alignment

### 1.1 Overview

Claude Code expects specific file locations and formats. The wrapper must generate these files at container startup to ensure proper integration.

### 1.2 Required File Locations

| File | Location | Purpose |
|------|----------|---------|
| `.mcp.json` | `/workspace/.mcp.json` | Project-scoped MCP servers |
| `settings.json` | `/home/claude/.claude/settings.json` | Permission rules, hooks, env vars |
| `CLAUDE.md` | `/workspace/.claude/CLAUDE.md` | Project memory and context |
| Skills | `/workspace/.claude/skills/` | Custom skill definitions |

### 1.3 Generated settings.json

The wrapper generates `/home/claude/.claude/settings.json` at startup:

```json
{
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
      "mcp__cc-docker__*"
    ],
    "deny": [],
    "defaultMode": "bypassPermissions"
  },
  "env": {
    "SESSION_ID": "${SESSION_ID}",
    "REDIS_URL": "${REDIS_URL}",
    "GATEWAY_URL": "${GATEWAY_URL}",
    "PARENT_SESSION_ID": "${PARENT_SESSION_ID}",
    "MCP_TIMEOUT": "30000",
    "MAX_MCP_OUTPUT_TOKENS": "50000"
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "/opt/wrapper/hooks/session-start.sh"
        }]
      }
    ]
  }
}
```

### 1.4 Generated .mcp.json

The wrapper generates `/workspace/.mcp.json` based on session configuration:

```json
{
  "mcpServers": {
    "cc-docker": {
      "type": "stdio",
      "command": "node",
      "args": ["/opt/cc-docker-mcp/index.js"],
      "env": {
        "SESSION_ID": "${SESSION_ID}",
        "REDIS_URL": "${REDIS_URL}",
        "GATEWAY_URL": "${GATEWAY_URL}"
      }
    },
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace", "/shared"]
    }
  }
}
```

### 1.5 Generated CLAUDE.md

The wrapper generates `/workspace/.claude/CLAUDE.md` with container context:

```markdown
# CC-Docker Session Context

## Session Information
- **Session ID**: ${SESSION_ID}
- **Parent Session**: ${PARENT_SESSION_ID:-"None (root session)"}
- **Container Role**: ${CONTAINER_ROLE:-"worker"}

## Available Capabilities

### MCP Servers
- **cc-docker**: Inter-session communication (spawn_child, send_to_child, etc.)
- **filesystem**: Enhanced file operations in /workspace and /shared

### Skills
- **/delegate-task**: Delegate work to a child session
- **/coordinate-children**: Manage multiple parallel child sessions
- **/child-status**: Monitor child session status

## Guidelines
- Use spawn_child for isolated, parallelizable tasks
- Use built-in Task tool for quick context lookups
- Stream output from long-running children to monitor progress
- Always clean up child sessions when done
```

### 1.6 Environment Variable Mapping

Claude Code recognizes these environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `MCP_TIMEOUT` | MCP server startup timeout (ms) | 10000 |
| `MCP_TOOL_TIMEOUT` | MCP tool execution timeout (ms) | 60000 |
| `MAX_MCP_OUTPUT_TOKENS` | Max tokens before warning | 25000 |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Max output tokens | 32000 |
| `BASH_DEFAULT_TIMEOUT_MS` | Default bash timeout | 120000 |
| `BASH_MAX_TIMEOUT_MS` | Maximum bash timeout | 600000 |

---

## 2. Inter-Session Communication

### 2.1 Overview

CC-Docker uses a **hybrid approach** for child sessions:

| Approach | Use Case | Isolation | Resources |
|----------|----------|-----------|-----------|
| **Docker Containers** | Heavy tasks, parallel work, long-running operations | Full (separate container) | High (new process) |
| **Built-in Subagents** | Quick lookups, code exploration, simple queries | Shared context | Low (same process) |

**Docker Container Children** (via CC-Docker MCP):
- Full isolation with separate Claude Code instance
- True parallelism (concurrent API calls)
- Own workspace and state
- Best for: multi-file refactoring, parallel code review, research tasks

**Built-in Subagents** (via Claude Code's Task tool):
- Shares parent context
- Sequential execution
- Lightweight and fast
- Best for: exploring codebase, quick file searches, simple questions

### 2.2 Capabilities

Parent CC instances can:
- **Spawn Docker children**: Launch isolated containers for heavy tasks
- **Use built-in subagents**: Quick tasks via Claude Code's Task tool
- **Send prompts**: Send follow-up prompts to running children
- **Stream output**: Receive real-time streaming output from children
- **Receive results**: Get final results when child completes
- **Query status**: Check child session status at any time
- **Terminate**: Stop child sessions cleanly

### 2.3 Communication Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Gateway                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   REST API  │    │  WebSocket  │    │   Pub/Sub   │         │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘         │
│         │                  │                  │                 │
│         └──────────────────┼──────────────────┘                 │
│                            │                                    │
│                     ┌──────▼──────┐                            │
│                     │    Redis    │                            │
│                     └──────┬──────┘                            │
└────────────────────────────┼────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼───────┐    ┌───────▼───────┐    ┌───────▼───────┐
│ Parent Session │    │ Child Session │    │ Child Session │
│   Container    │◄──►│   Container   │    │   Container   │
│                │    │               │    │               │
│  CC-Docker MCP │    │  CC-Docker MCP│    │  CC-Docker MCP│
│     Server     │    │     Server    │    │     Server    │
└────────────────┘    └───────────────┘    └───────────────┘
```

### 2.4 CC-Docker MCP Server

A custom MCP server running inside each container that enables inter-session communication.

#### Tools Provided

| Tool | Description |
|------|-------------|
| `spawn_child` | Spawn a new child session with initial prompt |
| `send_to_child` | Send a follow-up prompt to an existing child |
| `get_child_output` | Get streaming output from a child session |
| `get_child_result` | Get the final result from a completed child |
| `list_children` | List all child sessions with their status |
| `stop_child` | Terminate a running child session |
| `get_parent_context` | Get context/data from parent session |
| `notify_user` | Send a notification to the user via Discord |
| `ask_user` | Ask the user a question via Discord and wait for response |

#### Example Usage (from Claude Code inside container)

```
# Spawn a child to analyze a specific file
spawn_child(prompt="Analyze the security vulnerabilities in auth.py", task_type="security-review")

# Send follow-up to existing child
send_to_child(child_id="abc123", prompt="Focus specifically on SQL injection risks")

# Stream output from child
get_child_output(child_id="abc123", stream=true)

# Get final result
result = get_child_result(child_id="abc123", wait=true)
```

### 2.5 Redis Pub/Sub Channels

| Channel Pattern | Purpose |
|-----------------|---------|
| `session:{id}:output` | Streaming output from a session |
| `session:{id}:input` | Input queue for prompts |
| `session:{id}:control` | Control messages (stop, status) |
| `session:{id}:child:{child_id}` | Child-specific communication |
| `session:{id}:parent` | Messages to parent from children |

### 2.6 Bi-directional Message Flow

```
Parent                    Redis                     Child
  │                         │                         │
  │── spawn_child ─────────►│                         │
  │                         │──── create container ──►│
  │                         │                         │
  │                         │◄─── output stream ──────│
  │◄── stream output ───────│                         │
  │                         │                         │
  │── send_to_child ───────►│                         │
  │                         │──── input queue ───────►│
  │                         │                         │
  │                         │◄─── more output ────────│
  │◄── stream output ───────│                         │
  │                         │                         │
  │                         │◄─── final result ───────│
  │◄── result ──────────────│                         │
```

### 2.7 Discord Integration (Human-in-the-Loop)

CC-Docker enables direct communication between Claude Code sessions and users via Discord. This provides human-in-the-loop capabilities for long-running tasks.

#### 2.7.1 Discord MCP Tools

The CC-Docker MCP server includes two Discord tools for user communication:

**notify_user**: Fire-and-forget notifications
- Send progress updates, completion notifications, or alerts
- Non-blocking (returns immediately)
- Useful for keeping users informed of task progress

**ask_user**: Blocking questions that wait for user response
- Ask for decisions, clarifications, or approvals
- Blocks until user responds in Discord (with timeout)
- Enables human oversight at critical decision points

#### 2.7.2 notify_user Tool

```typescript
interface NotifyUserInput {
  message: string;          // Notification message (1-2000 chars)
  priority?: "normal" | "urgent";  // Default: "normal"
}

interface NotifyUserOutput {
  success: boolean;
  interaction_id: string;
}
```

**Example Usage**:
```
# From Claude Code inside container
notify_user(
  message="Analysis complete: Found 12 security issues in auth.py",
  priority="normal"
)

notify_user(
  message="🚨 Critical: Production deployment failed, manual intervention needed",
  priority="urgent"
)
```

**Behavior**:
- Message posted to configured Discord channel
- Returns immediately (non-blocking)
- No user response expected
- Tracked in database for audit

#### 2.7.3 ask_user Tool

```typescript
interface AskUserInput {
  question: string;         // Question text (1-2000 chars)
  timeout_seconds?: number; // Wait timeout (60-7200s, default: 1800)
  max_attempts?: number;    // Retry attempts (1-5, default: 3)
  priority?: "normal" | "urgent";
}

interface AskUserOutput {
  response: string;         // User's answer
  timed_out: boolean;       // Whether request timed out
  interaction_id: string;
}
```

**Example Usage**:
```
# Ask for user decision
response = ask_user(
  question="Should I proceed with refactoring auth.py? This will modify 15 functions.",
  timeout_seconds=300
)

if "yes" in response.lower():
    # Proceed with refactoring
    ...

# Ask which approach to use
choice = ask_user(
  question="Which library should I use for rate limiting: A) redis-rate-limit B) express-rate-limit C) rate-limiter-flexible?",
  timeout_seconds=600
)
```

**Behavior**:
- Creates a Discord thread with the question
- Blocks Claude Code execution until user responds
- User replies in the Discord thread
- Response returned to Claude Code
- On timeout, retries up to max_attempts
- Final timeout returns error to Claude Code

#### 2.7.4 Discord Architecture

```
Claude Code Session (Container)
    ↓ MCP Tool Call
CC-Docker MCP Server
    ↓ HTTP POST
Gateway API (/api/v1/discord/notify or /api/v1/discord/ask)
    ↓
Discord Service (discord.py bot)
    ↓
Discord Channel Thread
    ↓ User replies
Discord Bot Event Handler
    ↓ Store response
Redis (session:{id}:discord:response)
    ↓ Gateway polls
Gateway returns response to MCP
    ↓
Claude Code resumes with answer
```

#### 2.7.5 Configuration

**Environment Variables** (Gateway):
```bash
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=1234567890  # Channel to post to
DISCORD_QUESTION_TIMEOUT=1800   # Default timeout (30 min)
DISCORD_MAX_RETRIES=3
```

**MCP Configuration** (Auto-generated in `.mcp.json`):
```json
{
  "mcpServers": {
    "cc-docker": {
      "type": "stdio",
      "command": "node",
      "args": ["/opt/cc-docker-mcp/index.js"],
      "env": {
        "SESSION_ID": "${SESSION_ID}",
        "GATEWAY_URL": "${GATEWAY_URL}"
      }
    }
  }
}
```

#### 2.7.6 Database Tracking

All Discord interactions are persisted in the `discord_interactions` table:

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Unique interaction ID |
| session_id | UUID | CC session that created interaction |
| interaction_type | enum | "notification" or "question" |
| message | text | Notification message or question text |
| response | text | User's answer (for questions) |
| status | enum | "pending", "answered", "timeout", "completed" |
| discord_thread_id | string | Discord thread ID |
| attempt | int | Current retry attempt |
| max_attempts | int | Maximum retries |
| timeout_seconds | int | Timeout per attempt |
| priority | enum | "normal" or "urgent" |
| created_at | timestamp | When interaction was created |
| answered_at | timestamp | When user responded (questions only) |

#### 2.7.7 Use Cases

**Progress Notifications**:
```
# Notify user of milestones
notify_user("Starting code analysis...")
# ... work ...
notify_user("Analysis complete: 50 files, 12 issues found")
notify_user("Applying fixes...")
# ... work ...
notify_user("✅ All fixes applied successfully")
```

**Interactive Decisions**:
```
# Ask for approval before critical actions
response = ask_user(
  question="Ready to deploy to production. Proceed? (yes/no)",
  timeout_seconds=600,
  priority="urgent"
)

if response.lower() == "yes":
    deploy_to_production()
    notify_user("✅ Production deployment complete")
else:
    notify_user("Deployment cancelled by user")
```

**Long-Running Tasks**:
```
# Notify start
notify_user("Starting database migration (estimated 2 hours)...")

# Periodic progress updates
for i, table in enumerate(tables):
    migrate_table(table)
    if i % 10 == 0:
        notify_user(f"Progress: {i}/{len(tables)} tables migrated")

# Ask if issues found
if issues_found:
    response = ask_user(
      question=f"Found {len(issues)} data inconsistencies. Continue anyway? (yes/no)",
      timeout_seconds=1800
    )
    if response.lower() != "yes":
        rollback()
        return

# Notify completion
notify_user("✅ Migration complete: All tables migrated successfully")
```

**Multi-Agent Coordination**:
```
# Parent spawns multiple children
children = []
for i in range(5):
    child = spawn_child(prompt=f"Review module {i}")
    children.append(child)

notify_user(f"Spawned {len(children)} review sessions in parallel")

# Wait for completion
results = [get_child_result(c, wait=True) for c in children]

# Ask user about findings
issues = aggregate_issues(results)
if issues:
    response = ask_user(
      question=f"Found {len(issues)} issues across modules. Should I create fixes? (yes/no)",
      timeout_seconds=600
    )

    if response.lower() == "yes":
        apply_fixes(issues)
        notify_user("✅ All fixes applied")
```

#### 2.7.8 Error Handling

**Timeout Handling**:
```python
# In MCP server
try:
    response = await ask_user(question="...", timeout_seconds=300)
    return {"response": response}
except TimeoutError:
    # After max_attempts exhausted
    return {
        "error": "User did not respond within timeout",
        "timed_out": True
    }
```

**Discord Bot Offline**:
- Gateway returns 503 Service Unavailable
- MCP tool returns error to Claude Code
- Claude Code can decide to proceed without user input or retry

**Network Issues**:
- Automatic retries at HTTP layer
- Circuit breaker pattern prevents cascading failures
- Fallback to polling if WebSocket connection lost

#### 2.7.9 Security Considerations

1. **Authentication**: Only authenticated sessions can use Discord tools
2. **Rate Limiting**: Max 10 notifications per minute per session
3. **Message Validation**: Questions limited to 2000 chars, no @mentions
4. **Thread Isolation**: Each question gets its own Discord thread
5. **Audit Trail**: All interactions logged with session context
6. **No Sensitive Data**: Users warned not to paste credentials in Discord

#### 2.7.10 Setup Guide

See `docs/DISCORD_SETUP.md` for complete setup instructions:

1. Create Discord bot in Developer Portal
2. Enable "Message Content Intent"
3. Invite bot to server with permissions:
   - Send Messages
   - Create Public Threads
   - Read Message History
4. Set environment variables in gateway
5. Test with provided scripts

---

## 3. Pre-installed MCP Servers

### 3.1 Overview

The following MCP servers will be pre-installed in the CC-Docker container image:

| MCP Server | Purpose | Transport |
|------------|---------|-----------|
| **CC-Docker MCP** | Inter-session communication | stdio |
| **GitHub MCP** | Repository management, PRs, issues | HTTP |
| **Filesystem MCP** | Enhanced file operations | stdio |
| **PostgreSQL MCP** | Database queries and schema | stdio |
| **SQLite MCP** | Local database operations | stdio |
| **Playwright MCP** | Headless browser automation | stdio |

### 3.2 GitHub MCP Server

#### Capabilities
- Create, fork, and search repositories
- Manage branches and commits
- Create and review pull requests
- Manage issues and labels
- Search code across repositories

#### Configuration
```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "Bearer ${GITHUB_TOKEN}"
      }
    }
  }
}
```

#### Required Environment Variables
- `GITHUB_TOKEN`: Personal Access Token with `repo` scope

### 3.3 Filesystem MCP Server

#### Capabilities
- Read/write files across configured directories
- Create and manage directories
- Search files with glob patterns
- Get file metadata and directory trees

#### Configuration
```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace", "/shared"]
    }
  }
}
```

#### Accessible Directories
- `/workspace` - Session workspace (read/write)
- `/shared` - Shared storage across sessions (configurable)

### 3.4 PostgreSQL MCP Server

#### Capabilities
- Execute SQL queries (SELECT, INSERT, UPDATE, DELETE)
- Inspect database schema
- List tables and their structures
- Analyze query execution plans

#### Configuration
```json
{
  "mcpServers": {
    "postgres": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@bytebase/dbhub"],
      "env": {
        "DATABASE_URL": "${POSTGRES_URL}"
      }
    }
  }
}
```

#### Required Environment Variables
- `POSTGRES_URL`: PostgreSQL connection string

### 3.5 SQLite MCP Server

#### Capabilities
- Execute SQL queries on SQLite databases
- Create and manage local databases
- Schema inspection and management

#### Configuration
```json
{
  "mcpServers": {
    "sqlite": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@executeautomation/sqlite-mcp-server"],
      "env": {
        "SQLITE_DB_PATH": "/workspace/data.db"
      }
    }
  }
}
```

### 3.6 Playwright MCP Server

See [Section 5: Browser Automation](#5-browser-automation) for detailed configuration.

---

## 4. Custom CC-Docker Skills

### 4.1 Overview

Custom skills bundled with CC-Docker to enable multi-agent orchestration patterns. Skills follow Claude Code's skill format and are located in `/workspace/.claude/skills/`.

**Important**: Skills must be placed in `.claude/skills/` (not `/opt/cc-docker/skills/`) for Claude Code to discover them.

### 4.2 Skill Format

Skills use YAML frontmatter in a `SKILL.md` file:

```yaml
---
name: skill-name              # Required: lowercase, letters/numbers/hyphens
description: |                # Required: when to use this skill (max 1024 chars)
  Detailed description of what this skill does and when Claude should use it.
  Include trigger keywords for automatic discovery.
allowed-tools:                # Optional: restrict tool access
  - Read
  - Bash(mcp__cc-docker__*)
context: fork                 # Optional: run in isolated subagent context
agent: general-purpose        # Optional: agent type if context: fork
user-invocable: true          # Optional: show in /slash menu (default: true)
disable-model-invocation: false  # Optional: block Skill tool (default: false)
hooks:                        # Optional: component-scoped hooks
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./validate.sh"
---

# Skill Name

Instructions for Claude when this skill is active...
```

### 4.3 Skill: `delegate-task`

Delegates a task to a Docker container child session.

**Location**: `/workspace/.claude/skills/delegate-task/SKILL.md`

```yaml
---
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
```

### 4.4 Skill: `coordinate-children`

Coordinates multiple Docker container child sessions working in parallel.

**Location**: `/workspace/.claude/skills/coordinate-children/SKILL.md`

```yaml
---
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
```

### 4.5 Skill: `child-status`

Query and monitor Docker container child session status.

**Location**: `/workspace/.claude/skills/child-status/SKILL.md`

```yaml
---
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
```

---

## 5. Browser Automation

### 5.1 Overview

Headless Playwright provides browser automation capabilities for CC instances to:

- Scrape web pages for information
- Interact with web applications
- Test web UIs
- Automate web-based workflows

### 5.2 Playwright MCP Configuration

```json
{
  "mcpServers": {
    "playwright": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@executeautomation/playwright-mcp-server", "--headless"],
      "env": {
        "PLAYWRIGHT_BROWSERS_PATH": "/opt/playwright-browsers"
      }
    }
  }
}
```

### 5.3 Capabilities

| Tool | Description |
|------|-------------|
| `navigate` | Navigate to a URL |
| `click` | Click on an element |
| `fill` | Fill in form fields |
| `screenshot` | Capture page screenshot |
| `get_text` | Extract text from page |
| `evaluate` | Execute JavaScript |
| `wait_for` | Wait for element/condition |

### 5.4 Container Requirements

The Docker image must include:

```dockerfile
# Install Playwright and browsers
RUN npm install -g @executeautomation/playwright-mcp-server
RUN npx playwright install chromium --with-deps

# Set browser path
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
```

### 5.5 Usage Example

```
# Navigate to a page
navigate(url="https://github.com/anthropics/claude-code")

# Get page content
content = get_text(selector="article")

# Take a screenshot
screenshot(path="/workspace/screenshot.png")
```

### 5.6 Limitations

- Headless mode only (no display)
- Chromium browser only (for container size)
- No persistent browser sessions across container restarts
- Rate limiting recommended for external sites

---

## 6. Secrets Management

### 6.1 Overview

Secrets are passed to containers via environment variables at creation time. The gateway manages secret injection based on session configuration.

### 6.2 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Gateway                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 Secret Store                          │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐        │   │
│  │  │ GITHUB_*  │  │ POSTGRES_*│  │ API_KEYS  │        │   │
│  │  └───────────┘  └───────────┘  └───────────┘        │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│  Container Creation        │                                │
│  ─────────────────         ▼                                │
│  environment:                                               │
│    - GITHUB_TOKEN=${secrets.github_token}                   │
│    - POSTGRES_URL=${secrets.postgres_url}                   │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
               ┌─────────────────────────┐
               │    CC Container         │
               │                         │
               │  env:                   │
               │    GITHUB_TOKEN=***     │
               │    POSTGRES_URL=***     │
               └─────────────────────────┘
```

### 6.3 Supported Secrets

| Environment Variable | MCP Server | Purpose |
|---------------------|------------|---------|
| `GITHUB_TOKEN` | GitHub MCP | GitHub API authentication |
| `POSTGRES_URL` | PostgreSQL MCP | Database connection string |
| `SQLITE_DB_PATH` | SQLite MCP | Path to SQLite database |
| `ANTHROPIC_API_KEY` | Claude Code | API key (if not using OAuth) |
| `BROWSER_PROXY` | Playwright | Optional proxy configuration |

### 6.4 Gateway Configuration

Secrets are configured in the gateway's environment or a secrets file:

```yaml
# docker-compose.yml
services:
  gateway:
    environment:
      # Secrets to inject into containers
      CC_SECRET_GITHUB_TOKEN: ${GITHUB_TOKEN}
      CC_SECRET_POSTGRES_URL: ${POSTGRES_URL}
```

### 6.5 Session-level Secret Configuration

Sessions can request specific secrets via the API:

```json
POST /api/v1/sessions
{
  "workspace": { "type": "ephemeral" },
  "config": {
    "secrets": ["GITHUB_TOKEN", "POSTGRES_URL"],
    "mcp_servers": ["github", "postgres"]
  }
}
```

### 6.6 Security Considerations

- Secrets are never logged or exposed in API responses
- Containers cannot access secrets not explicitly granted
- Secret values are passed at container creation, not runtime
- Consider using Docker secrets for production deployments

---

## 7. Container Architecture

### 7.1 Updated Dockerfile

```dockerfile
FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    ca-certificates \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install MCP servers
RUN npm install -g \
    @modelcontextprotocol/server-filesystem \
    @executeautomation/playwright-mcp-server \
    @executeautomation/sqlite-mcp-server \
    @bytebase/dbhub

# Install Playwright browsers (Chromium only)
RUN npx playwright install chromium --with-deps
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

# Install uv for Python dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy wrapper code
COPY wrapper/ /opt/wrapper/

# Install wrapper dependencies using uv
WORKDIR /opt/wrapper
RUN uv sync --no-dev --no-install-project
ENV VIRTUAL_ENV=/opt/wrapper/.venv
ENV PATH="/opt/wrapper/.venv/bin:$PATH"
WORKDIR /

# Copy CC-Docker MCP server
COPY mcp-server/ /opt/cc-docker-mcp/
RUN cd /opt/cc-docker-mcp && npm install

# Copy custom skills
COPY skills/ /opt/cc-docker/skills/

# Copy MCP configuration
COPY mcp-config.json /opt/cc-docker/mcp-config.json

# Create non-root user
RUN useradd -m -s /bin/bash claude

# Create directories
RUN mkdir -p /workspace /shared && chown -R claude:claude /workspace /shared
RUN mkdir -p /home/claude/.claude && chown -R claude:claude /home/claude

# Switch to non-root user
USER claude
WORKDIR /workspace

# Entry point
ENTRYPOINT ["python3", "/opt/wrapper/main.py"]
```

### 7.2 MCP Configuration Template

**Template**: `/opt/cc-docker/templates/mcp.json.tmpl`
**Generated to**: `/workspace/.mcp.json`

The wrapper generates the MCP configuration from this template at startup:

```json
{
  "mcpServers": {
    "cc-docker": {
      "type": "stdio",
      "command": "node",
      "args": ["/opt/cc-docker-mcp/index.js"],
      "env": {
        "SESSION_ID": "${SESSION_ID}",
        "REDIS_URL": "${REDIS_URL}",
        "GATEWAY_URL": "${GATEWAY_URL}"
      }
    },
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace", "/shared"]
    },
    "playwright": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@executeautomation/playwright-mcp-server", "--headless"]
    },
    "sqlite": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@executeautomation/sqlite-mcp-server"]
    }
  },
  "conditionalServers": {
    "github": {
      "condition": "env:GITHUB_TOKEN",
      "config": {
        "type": "http",
        "url": "https://api.githubcopilot.com/mcp/",
        "headers": {
          "Authorization": "Bearer ${GITHUB_TOKEN}"
        }
      }
    },
    "postgres": {
      "condition": "env:POSTGRES_URL",
      "config": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@bytebase/dbhub"],
        "env": {
          "DATABASE_URL": "${POSTGRES_URL}"
        }
      }
    }
  }
}
```

### 7.3 Directory Structure

```
/opt/cc-docker/
├── mcp-server/              # CC-Docker MCP server source
│   ├── package.json
│   ├── index.js
│   └── tools/
│       ├── spawn-child.js
│       ├── send-to-child.js
│       ├── get-child-output.js
│       └── list-children.js
├── hooks/                    # Container lifecycle hooks
│   └── session-start.sh
└── templates/               # Configuration templates
    ├── settings.json.tmpl
    ├── mcp.json.tmpl
    └── CLAUDE.md.tmpl

/workspace/                   # Session workspace (mounted)
├── .claude/                  # Project-level Claude Code config
│   ├── CLAUDE.md             # Project memory (generated at startup)
│   ├── settings.json         # Project settings (generated at startup)
│   └── skills/               # Custom skills (copied at startup)
│       ├── delegate-task/
│       │   └── SKILL.md
│       ├── coordinate-children/
│       │   └── SKILL.md
│       └── child-status/
│           └── SKILL.md
├── .mcp.json                 # MCP server config (generated at startup)
└── [user files]              # Mounted or created files

/home/claude/.claude/         # User-level Claude Code config
├── settings.json             # User settings (generated at startup)
└── .credentials.json         # Auth credentials (mounted read-only)

/shared/                      # Shared storage across sessions (optional mount)
```

### 7.4 Wrapper Startup Sequence

The wrapper performs these steps at container startup:

1. **Generate configuration files**:
   - `/workspace/.mcp.json` from session config
   - `/workspace/.claude/settings.json` from session config
   - `/workspace/.claude/CLAUDE.md` with session context
   - `/home/claude/.claude/settings.json` with default permissions

2. **Copy skills to workspace**:
   - Copy `/opt/cc-docker/templates/skills/*` to `/workspace/.claude/skills/`

3. **Initialize Redis connection**:
   - Connect to Redis for pub/sub communication
   - Register session in active_sessions set

4. **Start health reporter**:
   - Send periodic heartbeats to Redis

5. **Enter input loop**:
   - Wait for prompts on Redis input queue
   - Execute Claude Code with prompt
   - Stream output to Redis output channel

---

## 8. Configuration

### 8.1 Gateway Environment Variables

```bash
# Required
REDIS_URL=redis://redis:6379
DATABASE_URL=sqlite:///data/cc-docker.db

# MCP Secrets (injected into containers)
CC_SECRET_GITHUB_TOKEN=ghp_xxx
CC_SECRET_POSTGRES_URL=postgresql://user:pass@host:5432/db

# Optional
CC_DEFAULT_MCP_SERVERS=filesystem,playwright,cc-docker
CC_ENABLE_GITHUB_MCP=true
CC_ENABLE_POSTGRES_MCP=true
```

### 8.2 Session Configuration API

```json
POST /api/v1/sessions
{
  "workspace": {
    "type": "ephemeral"
  },
  "config": {
    "timeout_seconds": 3600,
    "mcp_servers": ["cc-docker", "filesystem", "github", "playwright"],
    "secrets": ["GITHUB_TOKEN"],
    "skills": ["delegate-task", "coordinate-children"],
    "claude_config": {
      "permission_mode": "bypassPermissions",
      "allowed_tools": ["Read", "Write", "Edit", "Bash", "WebFetch"]
    }
  }
}
```

### 8.3 Per-Session MCP Overrides

```json
{
  "config": {
    "mcp_overrides": {
      "filesystem": {
        "args": ["/workspace", "/custom/path"]
      },
      "custom-server": {
        "type": "http",
        "url": "https://my-custom-mcp.example.com/mcp"
      }
    }
  }
}
```

---

## 9. Security Considerations

### 9.1 Prompt Injection Defense

MCP servers that fetch external content (web, databases, files) can expose Claude to prompt injection attacks. Implement these defenses:

#### Gateway-Level Defenses

```python
# Validate prompts before passing to containers
def validate_prompt(prompt: str) -> bool:
    """Reject prompts with obvious injection patterns."""
    injection_patterns = [
        r"ignore previous instructions",
        r"system prompt override",
        r"admin mode activate",
        r"<system>",
        r"\[INST\]",
    ]
    for pattern in injection_patterns:
        if re.search(pattern, prompt, re.IGNORECASE):
            return False
    return True
```

#### Container-Level Defenses

1. **Sandbox MCP output**: Treat all MCP tool results as untrusted
2. **Limit tool capabilities**: Use `allowed-tools` in skills to restrict actions
3. **Monitor for anomalies**: Log unusual tool usage patterns

### 9.2 Resource Limits

Prevent resource exhaustion attacks:

```yaml
# Container resource limits
resources:
  limits:
    cpus: "2"
    memory: "4G"
  reservations:
    cpus: "0.5"
    memory: "512M"

# Session limits
session:
  max_children_per_session: 5
  max_child_depth: 3
  child_timeout_seconds: 1800
  max_tokens_per_turn: 100000
```

### 9.3 Credential Protection

1. **Never log secrets**: Sanitize all logs before storage
2. **Rotate tokens**: Implement token rotation for long-running sessions
3. **Scope credentials**: Grant minimum required permissions per session
4. **Audit access**: Log all credential usage with session context

### 9.4 Container Isolation

Ensure proper container isolation:

```dockerfile
# Run as non-root user
USER claude

# Drop capabilities
docker run --cap-drop=ALL --cap-add=NET_BIND_SERVICE ...

# Read-only root filesystem (except /workspace, /tmp)
docker run --read-only --tmpfs /tmp ...

# No privileged mode
docker run --security-opt=no-new-privileges ...
```

### 9.5 Network Security

1. **Restrict egress**: Allow only required external hosts
2. **No inter-container networking**: Unless explicitly required
3. **TLS everywhere**: All internal communication uses TLS

```yaml
# Docker network with isolation
networks:
  cc-docker:
    driver: bridge
    internal: true  # No external access

  cc-docker-egress:
    driver: bridge
    # Explicit egress allowlist via firewall rules
```

### 9.6 Child Session Security

Prevent malicious child spawning:

1. **Depth limits**: Maximum 3 levels of child nesting
2. **Rate limits**: Maximum 5 children per minute per session
3. **Resource inheritance**: Children inherit parent's resource limits
4. **Credential scoping**: Children only get explicitly granted credentials

```python
def validate_child_spawn(parent_session, child_config):
    """Validate child spawn request."""
    # Check depth limit
    if parent_session.depth >= MAX_CHILD_DEPTH:
        raise ChildSpawnError("Maximum child depth exceeded")

    # Check rate limit
    recent_spawns = get_recent_spawns(parent_session.id, minutes=1)
    if len(recent_spawns) >= MAX_SPAWNS_PER_MINUTE:
        raise ChildSpawnError("Spawn rate limit exceeded")

    # Validate credentials
    for secret in child_config.get("secrets", []):
        if secret not in parent_session.granted_secrets:
            raise ChildSpawnError(f"Cannot grant unauthorized secret: {secret}")

    return True
```

---

## 10. Implementation Phases

### Phase 0: Configuration Alignment (Foundation)

**Goal**: Ensure wrapper generates proper Claude Code configuration files

**Tasks**:
1. Update wrapper to generate `/workspace/.mcp.json` at startup
2. Update wrapper to generate `/workspace/.claude/settings.json` at startup
3. Update wrapper to generate `/workspace/.claude/CLAUDE.md` with session context
4. Update wrapper to copy skills to `/workspace/.claude/skills/`
5. Validate Claude Code discovers and uses generated configuration
6. Test with existing session management infrastructure

**Deliverables**:
- Updated `wrapper/config.py` with file generation logic
- Configuration templates in `/opt/cc-docker/templates/`
- Integration tests for configuration generation

**Acceptance Criteria**:
- Claude Code loads MCP servers from generated `.mcp.json`
- Claude Code reads project context from generated `CLAUDE.md`
- Skills are discoverable via `/delegate-task`, etc.

### Phase 1: CC-Docker MCP Server (Core)

**Goal**: Enable basic inter-session communication via MCP

**Tasks**:
1. Create CC-Docker MCP server with Node.js (stdio transport)
2. Implement `spawn_child` tool (calls gateway API to create child container)
3. Implement `get_child_result` tool (polls gateway API for completion)
4. Implement `list_children` tool (queries gateway API)
5. Add gateway endpoint `/api/v1/sessions/{id}/spawn` for child creation
6. Test parent-child communication end-to-end

**Deliverables**:
- `/opt/cc-docker/mcp-server/` - MCP server source
- Updated gateway with spawn endpoint
- Integration tests

### Phase 2: Streaming & Bi-directional Communication

**Goal**: Full real-time communication between sessions

**Tasks**:
1. Implement `send_to_child` tool
2. Implement `get_child_output` with streaming
3. Implement `stop_child` tool
4. Add Redis pub/sub for child output forwarding
5. Update gateway to route child messages to parent
6. Test streaming output scenarios

**Deliverables**:
- Streaming output support
- Follow-up prompt capability
- Child termination support

### Phase 3: Pre-installed MCP Servers

**Goal**: Bundle useful MCP servers in container

**Tasks**:
1. Add Filesystem MCP server
2. Add Playwright MCP server (headless)
3. Add SQLite MCP server
4. Add PostgreSQL MCP support (conditional)
5. Add GitHub MCP support (conditional)
6. Update Dockerfile with dependencies
7. Create MCP configuration system

**Deliverables**:
- Updated Dockerfile with all MCP servers
- Configuration file for MCP servers
- Documentation for each MCP server

### Phase 4: Custom Skills

**Goal**: Provide orchestration skills for multi-agent patterns

**Tasks**:
1. Create `delegate-task` skill with proper YAML frontmatter
2. Create `coordinate-children` skill
3. Create `child-status` skill
4. Bundle skills in `/opt/cc-docker/templates/skills/` (copied to `/workspace/.claude/skills/` at startup)
5. Test skill auto-discovery by Claude Code
6. Test manual invocation via `/delegate-task`, etc.
7. Document skill usage patterns

**Deliverables**:
- `/opt/cc-docker/templates/skills/` directory with SKILL.md files
- Skill documentation with examples
- Integration tests for skill invocation

### Phase 5: Secrets Management

**Goal**: Secure credential handling for MCP servers

**Tasks**:
1. Implement gateway secret store
2. Add session-level secret requests
3. Implement container secret injection
4. Add conditional MCP server loading based on secrets
5. Security audit and hardening
6. Documentation for secret configuration

**Deliverables**:
- Secret management in gateway
- Per-session secret configuration
- Security documentation

### Phase 6: Testing & Documentation

**Goal**: Comprehensive testing and documentation

**Tasks**:
1. Unit tests for CC-Docker MCP server
2. Integration tests for inter-session communication
3. End-to-end tests for MCP servers
4. Performance testing for streaming
5. Update API documentation
6. Create user guides for each feature

**Deliverables**:
- Test suite
- API documentation
- User guides

---

## Appendix A: CC-Docker MCP Server API

### spawn_child

```typescript
interface SpawnChildInput {
  prompt: string;           // Initial prompt for child
  context?: object;         // Optional context data
  task_type?: string;       // Optional task categorization
  stream_output?: boolean;  // Whether to stream output (default: true)
  timeout_seconds?: number; // Child session timeout
}

interface SpawnChildOutput {
  child_session_id: string;
  status: "starting" | "idle" | "running";
}
```

### send_to_child

```typescript
interface SendToChildInput {
  child_session_id: string;
  prompt: string;
  wait_for_result?: boolean; // Whether to wait for completion
}

interface SendToChildOutput {
  message_id: string;
  status: "queued" | "processing";
}
```

### get_child_output

```typescript
interface GetChildOutputInput {
  child_session_id: string;
  stream?: boolean;        // Stream or get current buffer
  since_timestamp?: string; // Get output since timestamp
}

interface GetChildOutputOutput {
  output: string;
  is_complete: boolean;
  timestamp: string;
}
```

### get_child_result

```typescript
interface GetChildResultInput {
  child_session_id: string;
  wait?: boolean;          // Wait for completion if not done
  timeout_seconds?: number; // Wait timeout
}

interface GetChildResultOutput {
  status: "pending" | "completed" | "failed";
  result?: string;
  error?: string;
  usage?: {
    input_tokens: number;
    output_tokens: number;
  };
}
```

### list_children

```typescript
interface ListChildrenInput {
  status_filter?: string[]; // Filter by status
  include_completed?: boolean;
}

interface ListChildrenOutput {
  children: Array<{
    session_id: string;
    status: string;
    created_at: string;
    task_type?: string;
  }>;
}
```

### stop_child

```typescript
interface StopChildInput {
  child_session_id: string;
  force?: boolean; // Force immediate termination
}

interface StopChildOutput {
  success: boolean;
  final_status: string;
}
```

---

## Appendix B: Example Workflows

### B.1 Parallel Code Review

```
Parent prompt: "Review all Python files in /workspace/src for security issues"

Parent Claude Code actions:
1. List all .py files in /workspace/src
2. For each file, spawn_child with security review prompt
3. Monitor children with get_child_output (streaming)
4. Aggregate results with get_child_result
5. Generate summary report
```

### B.2 Research and Implementation Pipeline

```
Parent prompt: "Research best practices for rate limiting and implement in our API"

Parent Claude Code actions:
1. spawn_child for research task (browse docs, GitHub examples)
2. get_child_result to get research findings
3. spawn_child for implementation task (with research context)
4. Monitor implementation progress
5. spawn_child for testing task
6. Aggregate all results into final PR
```

### B.3 Multi-file Refactoring

```
Parent prompt: "Refactor the authentication module to use OAuth 2.0"

Parent Claude Code actions:
1. Analyze current auth implementation
2. Plan refactoring tasks (parallel-safe)
3. spawn_child for config changes
4. spawn_child for model changes
5. spawn_child for handler changes
6. Coordinate completion order (dependencies)
7. spawn_child for integration tests
8. Final verification and commit
```
