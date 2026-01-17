# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

CC-Docker (Claude Code Docker) is a Docker-based service that wraps Claude Code CLI with a FastAPI gateway, exposing a REST + WebSocket API for programmatic control of containerized Claude Code instances. It enables recursive orchestration, multi-agent coordination, and subscription-based pricing benefits.

**Key Design Philosophy**: Each Claude Code session runs in an isolated Docker container, with the wrapper process managing Claude CLI execution, configuration generation, and Redis pub/sub communication.

## Essential Commands

### Build and Setup

```bash
# Initial setup (builds container image + starts services)
./scripts/setup.sh

# Build only the Claude Code container image
./scripts/build-container.sh

# Build and start all services (gateway, redis, minio)
docker-compose build
docker-compose up -d

# View logs
docker-compose logs -f
docker-compose logs -f gateway  # Just gateway logs

# Stop all services
docker-compose down
```

### Development

```bash
# Gateway development (requires Python 3.12+)
cd gateway
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
JWT_SECRET=test-secret uvicorn app.main:app --reload

# Run tests
pip install -r tests/requirements.txt
pytest tests/ -v

# End-to-end test (requires services running)
./test_parent_child_e2e.sh
```

## Architecture

### Three-Layer Design

```
┌─────────────────────────────────────────────────────────┐
│ Gateway Layer (FastAPI)                                  │
│ - REST/WebSocket API                                     │
│ - JWT authentication                                     │
│ - Container lifecycle management (aiodocker)             │
│ - Session state tracking (PostgreSQL + Redis)            │
└──────────────────┬──────────────────────────────────────┘
                   │ Docker API
┌──────────────────▼──────────────────────────────────────┐
│ Container Layer (per-session isolation)                  │
│ - Node.js + Claude Code CLI                             │
│ - Python wrapper process                                 │
│ - MCP servers (filesystem, playwright, cc-docker, etc.)  │
│ - Dynamically generated config files                     │
└──────────────────┬──────────────────────────────────────┘
                   │ Redis Pub/Sub
┌──────────────────▼──────────────────────────────────────┐
│ Storage Layer                                            │
│ - Redis: real-time pub/sub, session state               │
│ - PostgreSQL: session metadata, message history          │
│ - MinIO: workspace snapshots, artifacts                 │
└─────────────────────────────────────────────────────────┘
```

### Critical Architecture Points

1. **Dynamic Configuration Generation**: The wrapper (`wrapper/config_generator.py`) generates Claude Code configuration files at container startup:
   - `/workspace/.mcp.json` - MCP server configurations
   - `/workspace/.claude/settings.json` - Project-level settings
   - `/workspace/.claude/CLAUDE.md` - Session context/memory
   - `/home/claude/.claude/settings.json` - User-level permissions

2. **Claude Code Execution**: Wrapper invokes Claude CLI with:
   ```bash
   claude -p "$PROMPT" \
       --dangerously-skip-permissions \
       --output-format stream-json \
       --cwd /workspace \
       --session-id "$SESSION_ID" \
       --resume "$SESSION_ID"  # For multi-turn conversations
   ```

3. **Pub/Sub Communication**:
   - Container publishes Claude's streaming output to `session:{id}:output` Redis channel
   - Gateway subscribes and forwards to WebSocket clients
   - Parent-child sessions communicate via dedicated channels

4. **Parent-Child Workspace Mounting**: Child containers mount their workspace under the parent's workspace at `/workspace/children/<child_id>/`, enabling direct file access without network transfers.

## Key Modules

### Gateway (`gateway/app/`)

- **`main.py`**: FastAPI application entry point, router registration, lifecycle management
- **`api/routes/sessions.py`**: Session CRUD (create, list, get, stop, delete)
- **`api/routes/chat.py`**: Send prompts to sessions (blocking and async modes)
- **`api/routes/spawn.py`**: Parent-child session spawning with workspace inheritance
- **`api/websocket/stream.py`**: WebSocket streaming of Claude output
- **`services/container.py`**: Docker container lifecycle management via aiodocker
- **`services/session.py`**: Session state management (SQLite + Redis coordination)
- **`services/pubsub.py`**: Redis pub/sub wrapper for inter-session communication
- **`services/storage.py`**: MinIO client for workspace snapshots (future use)
- **`core/config.py`**: Settings management via pydantic-settings
- **`core/security.py`**: JWT token validation (generation is external)
- **`db/database.py`**: SQLAlchemy async SQLite connection
- **`models/`**: Pydantic schemas for API requests/responses

### Wrapper (`wrapper/`)

- **`main.py`**: Entry point - orchestrates initialization and input loop
- **`config_generator.py`**: Generates Claude Code config files at startup (`.mcp.json`, `settings.json`, `CLAUDE.md`, skills)
- **`claude_runner.py`**: Subprocess management for Claude CLI execution
- **`stream_parser.py`**: Parses Claude's streaming JSON output
- **`redis_publisher.py`**: Publishes parsed output to Redis channels
- **`health.py`**: Periodic heartbeat reporting to Redis
- **`config.py`**: Container environment variable configuration

### MCP Server (`mcp-server/`)

Custom MCP server (`cc-docker`) running inside containers, exposing tools for inter-session communication:
- `spawn_child`: Create child session
- `send_to_child`: Send follow-up prompts
- `get_child_output`: Stream child output
- `get_child_result`: Get final results
- `list_children`: Query child sessions
- `stop_child`: Terminate children

### Skills (`skills/`)

Custom Claude Code skills (YAML frontmatter format):
- **`delegate-task/`**: Delegate work to isolated Docker child containers
- **`coordinate-children/`**: Orchestrate multiple parallel child sessions
- **`child-status/`**: Monitor child session progress/health

Skills are copied from `/opt/cc-docker/templates/skills/` to `/workspace/.claude/skills/` at container startup.

## Configuration Flow

1. **Gateway receives session creation request** with config (MCP servers, secrets, timeouts)
2. **Gateway creates Docker container** with environment variables:
   - `SESSION_ID`, `REDIS_URL`, `GATEWAY_URL`, `PARENT_SESSION_ID`
   - Secrets: `GITHUB_TOKEN`, `POSTGRES_URL`, etc. (from `CC_SECRET_*` env vars)
3. **Wrapper startup sequence**:
   - Generate `/workspace/.mcp.json` from templates + session config
   - Generate `/workspace/.claude/settings.json` with permissions
   - Generate `/workspace/.claude/CLAUDE.md` with session context
   - Copy skills to `/workspace/.claude/skills/`
   - Connect to Redis for pub/sub
4. **Claude Code discovers configuration** via standard file locations
5. **Wrapper enters input loop**, waiting for prompts on Redis input queue

## Development Guidelines

### Adding New API Endpoints

1. Create route handler in `gateway/app/api/routes/`
2. Define Pydantic schemas in `gateway/app/models/`
3. Add business logic to `gateway/app/services/`
4. Register router in `gateway/app/main.py`
5. Update SQLAlchemy models in `gateway/app/db/models.py` if needed

### Adding New MCP Server Support

1. Add npm package to `container/Dockerfile` (RUN npm install -g ...)
2. Add conditional config entry in wrapper's MCP template (`wrapper/config_generator.py`)
3. Add secret environment variable to `docker-compose.yml` (CC_SECRET_...)
4. Update gateway to inject secret at container creation (`gateway/app/services/container.py`)
5. Document usage in SPEC-PLUGINS.md

### Modifying Wrapper Behavior

- **Initialization**: Edit `wrapper/main.py` and `wrapper/config_generator.py`
- **Claude execution**: Edit `wrapper/claude_runner.py` (subprocess management)
- **Output handling**: Edit `wrapper/stream_parser.py` (JSON parsing)
- **Redis communication**: Edit `wrapper/redis_publisher.py`

### Testing Strategy

- **Unit tests**: Test individual modules (container management, parsers, config generation)
- **Integration tests**: Test gateway + Redis + Docker interaction
- **E2E tests**: Full parent-child session flows (see `test_parent_child_e2e.sh`)

## Common Patterns

### Session Lifecycle

```
Starting → Idle → Running → Idle → Stopped
                    ↓
                  Failed
```

- **Starting**: Container being created, wrapper initializing
- **Idle**: Ready for input, waiting on Redis input queue
- **Running**: Claude CLI actively processing prompt
- **Stopped**: Gracefully terminated
- **Failed**: Error/timeout/crash

### Parent-Child Communication Pattern

```python
# Parent spawns child via gateway API
POST /api/v1/sessions/{parent_id}/spawn
{
  "prompt": "Analyze auth.py for security issues",
  "workspace": {"type": "inherit"}  # Child mounts under /workspace/children/
}

# Child workspace appears at:
# /workspace/children/<child_id>/
# Parent can directly read child's outputs

# Child publishes output to:
# session:{child_id}:output

# Parent subscribes to:
# session:{parent_id}:children
# (receives child completion events)
```

### Credentials Injection

1. Set secrets in gateway environment: `CC_SECRET_GITHUB_TOKEN=ghp_xxx`
2. Request secrets in session config: `"secrets": ["GITHUB_TOKEN"]`
3. Gateway injects at container creation: `GITHUB_TOKEN=${CC_SECRET_GITHUB_TOKEN}`
4. Wrapper generates `.mcp.json` with `${GITHUB_TOKEN}` references
5. MCP servers access via environment variables

## Important Constraints

- **Claude Code CLI is the execution engine**: Don't bypass the CLI, work within its configuration expectations
- **Configuration must be in correct locations**: `.mcp.json` must be in `/workspace/`, not `/opt/cc-docker/`
- **Skills must be in `.claude/skills/`**: Not in `/opt/cc-docker/skills/`
- **Environment variables are set at container creation**: Cannot be changed after startup
- **Redis is the communication backbone**: All real-time state flows through pub/sub
- **Container isolation is critical**: Each session must be fully isolated for security

## Database (PostgreSQL)

### Overview

CC-Docker uses PostgreSQL 16 for all persistent data storage:
- Session metadata and state
- Message history
- Discord interaction tracking
- Parent-child session relationships

### Configuration

PostgreSQL is configured with production-ready settings in docker-compose.yml:
- **Max connections**: 200 (supports many concurrent sessions)
- **Shared buffers**: 256MB (effective caching)
- **Connection pooling**: 20 base + 10 overflow in SQLAlchemy
- **Pool recycling**: 1 hour (prevents stale connections)
- **Health checks**: Automatic restart on failure

### Connection String Format

```
postgresql+asyncpg://user:password@host:port/database
```

Environment variables:
- `POSTGRES_USER`: Database user (default: ccadmin)
- `POSTGRES_PASSWORD`: User password (CHANGE IN PRODUCTION)
- `POSTGRES_DB`: Database name (default: ccdocker)

### Common Operations

**Connect to database**:
```bash
docker exec -it cc-docker-postgres-1 psql -U ccadmin -d ccdocker
```

**View tables**:
```sql
\dt
```

**Query sessions**:
```sql
SELECT id, status, created_at FROM sessions ORDER BY created_at DESC LIMIT 10;
```

**Check connection count**:
```sql
SELECT count(*) FROM pg_stat_activity WHERE datname = 'ccdocker';
```

**Manual backup**:
```bash
docker exec cc-docker-postgres-1 pg_dump -U ccadmin ccdocker > backup.sql
```

**Restore backup**:
```bash
cat backup.sql | docker exec -i cc-docker-postgres-1 psql -U ccadmin ccdocker
```

### Performance Tuning

If experiencing high load, adjust in docker-compose.yml:
- Increase `shared_buffers` for more caching
- Increase `max_connections` for more concurrent sessions
- Adjust `work_mem` for complex queries

### Migrations

Schema changes are handled by SQLAlchemy's `create_all()` at startup. For production deployments, use Alembic for proper migrations.

## Troubleshooting

**Container fails to start**:
- Check gateway logs: `docker-compose logs -f gateway`
- Check PostgreSQL connectivity: `docker exec -it cc-docker-postgres-1 pg_isready`
- Check Redis connectivity: `docker exec -it cc-docker-redis-1 redis-cli ping`
- Verify container image exists: `docker images | grep cc-docker-container`

**Database connection errors**:
- Verify PostgreSQL is running: `docker-compose ps postgres`
- Check credentials in `.env` match docker-compose.yml
- Check connection pool isn't exhausted: See "Check connection count" above
- Review gateway logs: `docker-compose logs -f gateway | grep -i database`

**Claude Code not discovering MCP servers**:
- Verify `.mcp.json` exists in `/workspace/`: `docker exec <container> cat /workspace/.mcp.json`
- Check wrapper logs for config generation errors
- Ensure MCP server binaries are installed: `docker exec <container> which npx`

**Child session not spawning**:
- Check parent session status: `GET /api/v1/sessions/{parent_id}`
- Verify `CC_DEFAULT_MCP_SERVERS` includes `cc-docker` in docker-compose.yml
- Check gateway has access to Docker socket: `/var/run/docker.sock` mounted

**Streaming output not appearing**:
- Verify Redis pub/sub working: `docker exec -it cc-docker-redis redis-cli SUBSCRIBE session:*`
- Check WebSocket connection in browser dev tools
- Verify wrapper is publishing: Check container logs for "Publishing output"

## Discord Integration

### Overview

CC instances can communicate with you via Discord using two MCP tools:
- **`notify_user`**: Fire-and-forget notifications (completions, progress updates)
- **`ask_user`**: Blocking questions that wait for your response

### Setup

1. **Create Discord bot**: Follow `docs/DISCORD_SETUP.md` for step-by-step instructions
2. **Configure environment**: Add `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` to `.env`
3. **Restart gateway**: `docker-compose restart gateway`

### Architecture Flow

```
CC Container (calls MCP tool)
    ↓
notify_user/ask_user → MCP Server → Gateway API
    ↓
Gateway Discord Service → Discord Bot → Discord Channel
    ↓
User replies in Discord thread
    ↓
Discord Bot → Redis → Gateway API unblocks → MCP returns response
    ↓
CC Container resumes with user's answer
```

### Key Components

- **`gateway/app/services/discord.py`**: Discord bot implementation using discord.py
- **`gateway/app/api/routes/discord.py`**: API endpoints (`/notify`, `/ask`)
- **`gateway/app/db/models.py`**: `DiscordInteraction` model for tracking questions
- **`mcp-server/index.js`**: `notify_user` and `ask_user` tool implementations

### How It Works

**Notifications** (`notify_user`):
1. MCP tool calls gateway `/api/v1/discord/notify`
2. Gateway posts message to Discord channel
3. Returns immediately (non-blocking)

**Questions** (`ask_user`):
1. MCP tool calls gateway `/api/v1/discord/ask` (blocks)
2. Gateway creates thread in Discord with question
3. Gateway polls Redis for user response
4. User replies in Discord thread
5. Discord bot stores response in Redis
6. Gateway unblocks and returns response to MCP
7. MCP returns response to Claude Code

**Retry Logic**:
- Timeout: 30 minutes per attempt (configurable)
- Max attempts: 3 (configurable)
- Each timeout triggers a retry message in the Discord thread
- Final timeout returns error to Claude Code

### Adding New Discord Features

**Add a new Discord message type**:
1. Update `DiscordInteraction` model in `gateway/app/db/models.py`
2. Add method to `CCDiscordBot` class in `gateway/app/services/discord.py`
3. Add API endpoint in `gateway/app/api/routes/discord.py`
4. Add MCP tool in `mcp-server/index.js`

**Customize Discord message formatting**:
- Edit `_format_question_message()` in `gateway/app/services/discord.py`
- Modify emoji, layout, or add embeds

### Troubleshooting

**Bot is offline**:
- Check `DISCORD_BOT_TOKEN` is correct in `.env`
- Verify "Message Content Intent" enabled in Discord Developer Portal
- Check gateway logs: `docker-compose logs -f gateway | grep -i discord`

**Questions timeout immediately**:
- Verify Redis is running: `docker-compose ps redis`
- Check `DISCORD_QUESTION_TIMEOUT` setting in `.env`
- Ensure user has access to Discord channel

**Messages not appearing**:
- Verify `DISCORD_CHANNEL_ID` is correct
- Check bot has permissions: "Send Messages", "Create Threads", "Read Message History"
- Test with `/api/v1/discord/notify` endpoint manually

## Security Notes

- **JWT tokens**: Gateway validates but does NOT generate tokens (external responsibility)
- **Secrets**: Never log secrets, sanitize all log output in `gateway/app/services/`
- **Container isolation**: Containers run as non-root user `claude` (see Dockerfile)
- **`--dangerously-skip-permissions`**: Safe due to container isolation + pre-defined allowed-tools
- **Network isolation**: Use `cc-internal` network for Redis/MinIO, `cc-external` only when needed
- **Resource limits**: Set in docker-compose.yml to prevent DoS (2 CPU, 4GB RAM default)
- **Discord tokens**: Never commit `DISCORD_BOT_TOKEN` to git; store in `.env` only
