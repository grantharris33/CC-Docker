# Claude Code Docker Wrapper - Technical Specification

## Project Overview

A Docker-based service that wraps Claude Code with a FastAPI server, providing an API for external applications to control and interact with Claude Code instances. The system enables recursive orchestration where Claude Code instances can spawn and coordinate with other Claude Code instances.

**Project Codename**: `cc-docker` (Claude Code Docker)

---

## Table of Contents

1. [Goals & Non-Goals](#goals--non-goals)
2. [Architecture Overview](#architecture-overview)
3. [Component Design](#component-design)
4. [API Specification](#api-specification)
5. [Container Management](#container-management)
6. [Storage Architecture](#storage-architecture)
7. [Communication Patterns](#communication-patterns)
8. [Orchestration & Recursion](#orchestration--recursion)
9. [Security Model](#security-model)
10. [Observability](#observability)
11. [Deployment](#deployment)
12. [Open Questions](#open-questions)
13. [Reference Projects](#reference-projects)

---

## Goals & Non-Goals

### Goals

1. **API Wrapper**: Provide a REST + WebSocket API to interact with Claude Code programmatically
2. **Container Isolation**: Run each Claude Code session in an isolated Docker container
3. **Session Management**: Support multi-turn conversations with session persistence
4. **Streaming Output**: Stream Claude Code's JSON output to clients in real-time
5. **Recursive Orchestration**: Allow Claude Code instances to spawn child instances
6. **Workspace Management**: Optional persistence of project workspaces between sessions
7. **Extensibility**: Design for future orchestration features (multi-agent coordination)

### Non-Goals (Phase 1)

1. Multi-node clustering / Kubernetes (Docker Compose only for now)
2. OAuth token generation (separate project)
3. Web UI for human interaction (API-only)
4. Full multi-agent swarm intelligence (future phase)
5. Built-in git operations (delegate to Claude Code)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Docker Compose Stack                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐   │
│  │   FastAPI       │     │     Redis       │     │     MinIO       │   │
│  │   Gateway       │◄───►│   (pub/sub,     │     │   (workspaces,  │   │
│  │   (Port 8000)   │     │    queues)      │     │    artifacts)   │   │
│  └────────┬────────┘     └─────────────────┘     └─────────────────┘   │
│           │                       ▲                       ▲             │
│           │                       │                       │             │
│           ▼                       │                       │             │
│  ┌─────────────────┐              │                       │             │
│  │  Container      │              │                       │             │
│  │  Manager        │──────────────┴───────────────────────┘             │
│  │  (Docker API)   │                                                    │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           │ spawns/manages                                              │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Claude Code Containers                        │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │   │
│  │  │ Session 1 │  │ Session 2 │  │ Session 3 │  │ Session N │    │   │
│  │  │ ┌───────┐ │  │ ┌───────┐ │  │ ┌───────┐ │  │ ┌───────┐ │    │   │
│  │  │ │CC Wrap│ │  │ │CC Wrap│ │  │ │CC Wrap│ │  │ │CC Wrap│ │    │   │
│  │  │ └───┬───┘ │  │ └───┬───┘ │  │ └───┬───┘ │  │ └───┬───┘ │    │   │
│  │  │     │     │  │     │     │  │     │     │  │     │     │    │   │
│  │  │ ┌───▼───┐ │  │ ┌───▼───┐ │  │ ┌───▼───┐ │  │ ┌───▼───┐ │    │   │
│  │  │ │Claude │ │  │ │Claude │ │  │ │Claude │ │  │ │Claude │ │    │   │
│  │  │ │ Code  │ │  │ │ Code  │ │  │ │ Code  │ │  │ │ Code  │ │    │   │
│  │  │ └───────┘ │  │ └───────┘ │  │ └───────┘ │  │ └───────┘ │    │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────┐                                                   │
│  │     SQLite      │  (session metadata, history)                      │
│  │   (Volume)      │                                                   │
│  └─────────────────┘                                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Design

### 1. FastAPI Gateway (`/gateway`)

The main API server that handles all external requests.

**Responsibilities:**
- REST API endpoints for session management
- WebSocket endpoints for streaming
- JWT token validation
- Request routing to containers
- Prometheus metrics endpoint

**Technology:**
- Python 3.12+
- FastAPI + Uvicorn
- Pydantic for validation
- `aiodocker` for Docker API
- `aioredis` for Redis
- `aiobotocore` for MinIO (S3-compatible)

**Key Files:**
```
gateway/
├── main.py              # FastAPI app entry
├── api/
│   ├── routes/
│   │   ├── sessions.py  # Session CRUD
│   │   ├── chat.py      # Chat/prompt endpoints
│   │   ├── spawn.py     # Child instance spawning
│   │   └── health.py    # Health checks
│   └── websocket/
│       └── stream.py    # WebSocket streaming
├── core/
│   ├── config.py        # Settings
│   ├── security.py      # JWT validation
│   └── dependencies.py  # DI
├── services/
│   ├── container.py     # Container management
│   ├── session.py       # Session state
│   ├── storage.py       # MinIO operations
│   └── pubsub.py        # Redis pub/sub
├── models/
│   ├── session.py       # Session schema
│   ├── message.py       # Message schema
│   └── container.py     # Container schema
└── db/
    ├── database.py      # SQLite connection
    └── models.py        # SQLAlchemy models
```

### 2. Claude Code Wrapper (`/wrapper`)

Python process running inside each Claude Code container that wraps the Claude Code CLI.

**Responsibilities:**
- Launch Claude Code with proper arguments (`--dangerously-skip-permissions`, `--output-format stream-json`)
- Capture and parse JSON streaming output
- Publish output to Redis pub/sub channel
- Handle stdin for multi-turn conversations
- Report health status to gateway
- Handle graceful shutdown

**Key Files:**
```
wrapper/
├── main.py              # Entry point
├── claude_runner.py     # Claude Code process management
├── stream_parser.py     # JSON stream parsing
├── redis_publisher.py   # Pub/sub publishing
├── health.py            # Health reporting
└── config.py            # Environment config
```

**Claude Code Invocation:**
```bash
claude -p "$PROMPT" \
    --dangerously-skip-permissions \
    --output-format stream-json \
    --cwd /workspace \
    --session-id "$SESSION_ID" \
    --resume "$SESSION_ID"  # For follow-up messages
```

### 3. Container Image (`/container`)

Docker image containing Claude Code and the wrapper.

**Base Image:** `node:20-slim`

**Installed Components:**
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Python 3.12 + wrapper dependencies
- Git, common dev tools

**Dockerfile Structure:**
```dockerfile
FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.12 python3-pip git curl \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code
RUN npm install -g @anthropic-ai/claude-code

# Install wrapper
COPY wrapper/ /opt/wrapper/
RUN pip install -r /opt/wrapper/requirements.txt

# Pre-authenticated Claude config will be mounted at runtime
# /root/.claude/ -> mounted volume with OAuth token

WORKDIR /workspace
ENTRYPOINT ["python3", "/opt/wrapper/main.py"]
```

---

## API Specification

### Base URL
```
http://localhost:8000/api/v1
```

### Authentication

All endpoints require JWT token in Authorization header:
```
Authorization: Bearer <jwt_token>
```

JWT payload should contain:
```json
{
  "sub": "user_id",
  "exp": 1234567890,
  "iat": 1234567890
}
```

### Endpoints

#### Sessions

**Create Session**
```http
POST /sessions
Content-Type: application/json

{
  "workspace": {
    "type": "ephemeral" | "persistent",
    "id": "workspace-uuid",        // Required if type=persistent
    "git_repo": "https://...",     // Optional: clone repo
    "git_branch": "main"           // Optional: branch to checkout
  },
  "config": {
    "timeout_seconds": 3600,       // Container timeout
    "model": "opus-4",             // Claude model
    "system_prompt": "...",        // Optional: custom system prompt
    "allowed_tools": ["*"],        // Tool permissions
    "mcp_servers": {}              // Optional: MCP server config
  },
  "parent_session_id": "uuid"      // Optional: for child sessions
}

Response: 201 Created
{
  "session_id": "uuid",
  "status": "starting",
  "container_id": "docker-container-id",
  "created_at": "2025-01-15T...",
  "websocket_url": "ws://localhost:8000/api/v1/sessions/{session_id}/stream"
}
```

**Get Session**
```http
GET /sessions/{session_id}

Response: 200 OK
{
  "session_id": "uuid",
  "status": "running" | "idle" | "stopped" | "failed",
  "container_id": "...",
  "created_at": "...",
  "last_activity": "...",
  "parent_session_id": null | "uuid",
  "child_session_ids": ["uuid", ...],
  "total_cost_usd": 0.05,
  "total_turns": 5
}
```

**List Sessions**
```http
GET /sessions?status=running&limit=50&offset=0

Response: 200 OK
{
  "sessions": [...],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

**Stop Session**
```http
POST /sessions/{session_id}/stop

Response: 200 OK
{
  "session_id": "uuid",
  "status": "stopped"
}
```

**Delete Session**
```http
DELETE /sessions/{session_id}

Response: 204 No Content
```

#### Chat

**Send Message**
```http
POST /sessions/{session_id}/chat
Content-Type: application/json

{
  "prompt": "Fix the bug in auth.py",
  "stream": true,                   // Whether to use WebSocket streaming
  "timeout_seconds": 300            // Optional: override default timeout
}

Response: 202 Accepted (if stream=true)
{
  "message_id": "uuid",
  "status": "processing"
}

Response: 200 OK (if stream=false, blocks until complete)
{
  "message_id": "uuid",
  "type": "result",
  "subtype": "success",
  "result": "I've fixed the bug...",
  "duration_ms": 5000,
  "total_cost_usd": 0.01,
  "usage": {
    "input_tokens": 500,
    "output_tokens": 200
  }
}
```

**Get Message Status**
```http
GET /sessions/{session_id}/messages/{message_id}

Response: 200 OK
{
  "message_id": "uuid",
  "status": "processing" | "completed" | "failed",
  "result": {...}  // Present if completed
}
```

#### Spawn (Child Instances)

**Spawn Child Session**
```http
POST /sessions/{session_id}/spawn
Content-Type: application/json

{
  "prompt": "Analyze the database schema",
  "workspace": {
    "type": "inherit" | "clone" | "ephemeral",
    "snapshot": true                // Take snapshot of parent workspace
  },
  "config": {
    "timeout_seconds": 1800
  },
  "callback": {
    "type": "pubsub",               // or "webhook"
    "channel": "session:{parent_id}:children"  // Redis channel
  }
}

Response: 201 Created
{
  "child_session_id": "uuid",
  "status": "starting",
  "parent_session_id": "uuid"
}
```

#### WebSocket Streaming

**Connect to Stream**
```
WS /sessions/{session_id}/stream
```

**Client -> Server Messages:**
```json
{
  "type": "prompt",
  "prompt": "Your message here"
}

{
  "type": "ping"
}
```

**Server -> Client Messages:**
```json
// Claude Code output (stream-json format, passed through)
{
  "type": "assistant",
  "message": {
    "type": "text",
    "text": "I'll help you..."
  }
}

{
  "type": "tool_use",
  "tool": "Read",
  "input": {"file_path": "/workspace/auth.py"}
}

{
  "type": "result",
  "subtype": "success",
  "result": "Task completed",
  "total_cost_usd": 0.02,
  "usage": {...}
}

// System messages
{
  "type": "system",
  "event": "session_started" | "session_stopped" | "error",
  "data": {...}
}

{
  "type": "child_result",
  "child_session_id": "uuid",
  "result": {...}
}

{
  "type": "pong"
}
```

#### Health & Metrics

**Health Check**
```http
GET /health

Response: 200 OK
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "minio": "healthy",
    "docker": "healthy"
  }
}
```

**Prometheus Metrics**
```http
GET /metrics

Response: 200 OK
# HELP cc_docker_sessions_total Total sessions created
# TYPE cc_docker_sessions_total counter
cc_docker_sessions_total{status="running"} 10
...
```

---

## Container Management

### Lifecycle

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Starting │────►│  Running │────►│   Idle   │────►│ Stopped  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                      │                 │
                      │                 │ timeout
                      │                 ▼
                      │           ┌──────────┐
                      └──────────►│  Failed  │
                         error    └──────────┘
```

### States

| State | Description |
|-------|-------------|
| `starting` | Container is being created and initialized |
| `running` | Claude Code is actively processing a request |
| `idle` | Container is running but waiting for input |
| `stopped` | Container was gracefully stopped |
| `failed` | Container crashed or timed out |

### Container Configuration

**Resource Limits:**
```yaml
resources:
  limits:
    cpus: '2'
    memory: 4G
  reservations:
    cpus: '0.5'
    memory: 512M
```

**Network:**
- Containers join a dedicated Docker network
- Can communicate with Redis/MinIO via service names
- Optionally: network isolation for untrusted workloads

**Volumes:**
```yaml
volumes:
  - type: bind
    source: /path/to/claude-config
    target: /root/.claude
    read_only: true
  - type: volume
    source: session-{session_id}
    target: /workspace
```

### Timeouts

| Timeout | Default | Description |
|---------|---------|-------------|
| `startup_timeout` | 60s | Max time to start container |
| `idle_timeout` | 300s | Stop container after idle period |
| `session_timeout` | 3600s | Max session duration |
| `request_timeout` | 600s | Max time for single request |

---

## Storage Architecture

### SQLite (Session Metadata)

**Location:** `/data/cc-docker.db` (Docker volume)

**Schema:**
```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    container_id TEXT,
    parent_session_id TEXT REFERENCES sessions(id),
    workspace_type TEXT NOT NULL,  -- 'ephemeral' or 'persistent'
    workspace_id TEXT,             -- MinIO bucket/path for persistent
    config JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stopped_at TIMESTAMP,
    total_cost_usd REAL DEFAULT 0,
    total_turns INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,            -- 'user' or 'assistant'
    content TEXT NOT NULL,
    cost_usd REAL DEFAULT 0,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_parent ON sessions(parent_session_id);
CREATE INDEX idx_messages_session ON messages(session_id);
```

### Redis (Real-time State)

**Data Structures:**

```redis
# Session state (hash)
session:{session_id}:state
  status: "running"
  container_id: "abc123"
  last_heartbeat: "2025-01-15T..."

# Message queue for session input
session:{session_id}:input (list)
  [prompt1, prompt2, ...]

# Pub/sub channels
session:{session_id}:output       # Stream output to clients
session:{session_id}:children     # Child session results
session:{session_id}:control      # Control messages (stop, etc.)

# Active sessions set
active_sessions (set)
  [session_id_1, session_id_2, ...]
```

**Pub/Sub Message Format:**
```json
{
  "type": "output" | "result" | "error" | "child_result",
  "session_id": "uuid",
  "timestamp": "2025-01-15T...",
  "data": {...}
}
```

### MinIO (Workspaces & Artifacts)

**Bucket Structure:**
```
cc-docker/
├── workspaces/
│   ├── {workspace_id}/
│   │   ├── snapshot-{timestamp}.tar.gz  # Workspace snapshots
│   │   └── current/                     # Current state (synced)
│   └── ...
├── artifacts/
│   ├── {session_id}/
│   │   ├── logs/
│   │   ├── outputs/
│   │   └── metadata.json
│   └── ...
└── claude-configs/
    └── {config_id}/
        └── .claude/                     # Pre-auth Claude config
```

---

## Communication Patterns

### Request Flow (Synchronous)

```
Client                Gateway              Container           Redis
  │                      │                    │                  │
  │  POST /chat          │                    │                  │
  │─────────────────────►│                    │                  │
  │                      │  Create container  │                  │
  │                      │───────────────────►│                  │
  │                      │                    │  Subscribe       │
  │                      │                    │─────────────────►│
  │                      │                    │                  │
  │                      │                    │  Run Claude      │
  │                      │                    │  ────────────    │
  │                      │                    │                  │
  │                      │                    │  Publish output  │
  │                      │◄───────────────────│◄─────────────────│
  │                      │                    │                  │
  │  Response            │                    │                  │
  │◄─────────────────────│                    │                  │
```

### Request Flow (Streaming)

```
Client                Gateway              Container           Redis
  │                      │                    │                  │
  │  WS Connect          │                    │                  │
  │─────────────────────►│                    │                  │
  │  {"type":"prompt"}   │                    │                  │
  │─────────────────────►│  Push to queue     │                  │
  │                      │─────────────────────────────────────►│
  │                      │                    │  Pop from queue  │
  │                      │                    │◄─────────────────│
  │                      │                    │                  │
  │                      │                    │  Run Claude      │
  │                      │  Subscribe to      │  ────────────    │
  │                      │  output channel    │                  │
  │                      │◄─────────────────────────────────────│
  │                      │                    │  Publish chunks  │
  │  Stream chunks       │◄───────────────────│─────────────────►│
  │◄─────────────────────│                    │                  │
  │  Stream chunks       │                    │                  │
  │◄─────────────────────│                    │                  │
  │  {"type":"result"}   │                    │                  │
  │◄─────────────────────│                    │                  │
```

### Child Instance Communication

```
Parent Container       Gateway              Child Container     Redis
       │                  │                       │               │
       │  POST /spawn     │                       │               │
       │─────────────────►│                       │               │
       │                  │  Create child         │               │
       │                  │──────────────────────►│               │
       │                  │                       │               │
       │  Subscribe to    │                       │               │
       │  children channel│                       │               │
       │──────────────────────────────────────────────────────────►
       │                  │                       │               │
       │                  │                       │  Run Claude   │
       │                  │                       │  ──────────   │
       │                  │                       │               │
       │                  │                       │  Publish result
       │◄─────────────────────────────────────────│──────────────►│
       │                  │                       │               │
       │  Continue with   │                       │               │
       │  child result    │                       │               │
```

---

## Orchestration & Recursion

### Spawning Child Instances

When a Claude Code instance needs to spawn a child:

1. **From within Claude Code**: The wrapper exposes an MCP tool or API endpoint that Claude can call
2. **Wrapper intercepts**: The wrapper catches the spawn request
3. **Gateway creates child**: Wrapper calls gateway API to create child session
4. **Subscribe to results**: Parent subscribes to Redis channel for child results
5. **Receive callback**: When child completes, result is published and parent continues

### MCP Tool for Spawning

The wrapper can expose an MCP server with a spawn tool:

```json
{
  "mcpServers": {
    "cc-docker": {
      "type": "stdio",
      "command": "python",
      "args": ["/opt/wrapper/mcp_server.py"]
    }
  }
}
```

**Spawn Tool Schema:**
```json
{
  "name": "spawn_claude_instance",
  "description": "Spawn a child Claude Code instance for parallel work",
  "input_schema": {
    "type": "object",
    "properties": {
      "prompt": {
        "type": "string",
        "description": "The task for the child instance"
      },
      "workspace_mode": {
        "type": "string",
        "enum": ["inherit", "clone", "ephemeral"],
        "default": "inherit"
      },
      "wait_for_result": {
        "type": "boolean",
        "default": true
      }
    },
    "required": ["prompt"]
  }
}
```

### Depth Limits

To prevent runaway recursion:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_depth` | 5 | Maximum spawn depth |
| `max_children` | 10 | Max children per session |
| `max_total_instances` | 50 | Max total instances in tree |

---

## Security Model

### JWT Authentication

- All API requests require valid JWT token
- Tokens are validated but not generated by this service
- Token claims used for:
  - User identification (`sub`)
  - Expiration checking (`exp`)
  - Optional: rate limiting, quotas

### Claude Code Authentication

- Pre-authenticated Claude config files stored in MinIO
- Mounted read-only into containers
- Config contains OAuth token for Anthropic API
- **Note**: Token generation is out of scope (separate project)

### Container Isolation

- Each session runs in isolated container
- Containers have limited network access:
  - Can reach Redis, MinIO (internal services)
  - Cannot reach gateway API directly (prevents spoofing)
  - Internet access: configurable per session
- Resource limits prevent DoS
- `--dangerously-skip-permissions` is safe due to container isolation

### Network Security

```yaml
networks:
  cc-internal:
    driver: bridge
    internal: true      # No external access
  cc-external:
    driver: bridge      # For containers needing internet
```

---

## Observability

### Logging

**Format:** Structured JSON logs

```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "level": "INFO",
  "service": "gateway",
  "session_id": "uuid",
  "message": "Session started",
  "extra": {
    "container_id": "abc123",
    "workspace_type": "ephemeral"
  }
}
```

**Log Levels:**
- `DEBUG`: Detailed debugging (not in prod)
- `INFO`: Normal operations
- `WARNING`: Recoverable issues
- `ERROR`: Failures requiring attention

### Metrics (Prometheus)

**Gateway Metrics:**
```
# Sessions
cc_docker_sessions_total{status}
cc_docker_sessions_active
cc_docker_session_duration_seconds{quantile}

# Requests
cc_docker_requests_total{endpoint,method,status}
cc_docker_request_duration_seconds{endpoint,quantile}

# Containers
cc_docker_containers_total{status}
cc_docker_container_startup_seconds{quantile}

# Claude Code
cc_docker_claude_cost_usd_total
cc_docker_claude_tokens_total{type}  # input, output
cc_docker_claude_turns_total

# Resources
cc_docker_redis_connections
cc_docker_minio_operations_total{operation}
```

**Container Metrics (per session):**
```
cc_docker_container_cpu_usage_percent
cc_docker_container_memory_usage_bytes
cc_docker_container_network_rx_bytes
cc_docker_container_network_tx_bytes
```

---

## Deployment

### Docker Compose

```yaml
version: '3.8'

services:
  gateway:
    build: ./gateway
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///data/cc-docker.db
      - REDIS_URL=redis://redis:6379
      - MINIO_URL=http://minio:9000
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
      - JWT_SECRET=${JWT_SECRET}
      - DOCKER_HOST=unix:///var/run/docker.sock
    volumes:
      - ./data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    depends_on:
      - redis
      - minio
    networks:
      - cc-internal
      - cc-external

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    networks:
      - cc-internal

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ACCESS_KEY}
      - MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY}
    volumes:
      - minio-data:/data
    ports:
      - "9001:9001"  # Console (optional)
    networks:
      - cc-internal

volumes:
  redis-data:
  minio-data:

networks:
  cc-internal:
    internal: true
  cc-external:
```

### Environment Variables

```bash
# Required
JWT_SECRET=your-jwt-secret-key
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Optional
LOG_LEVEL=INFO
CONTAINER_TIMEOUT_DEFAULT=3600
CONTAINER_IDLE_TIMEOUT=300
MAX_SESSIONS_PER_USER=10
MAX_SPAWN_DEPTH=5
```

### Directory Structure

```
cc-docker/
├── docker-compose.yml
├── .env.example
├── gateway/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── ...
├── wrapper/
│   ├── requirements.txt
│   └── ...
├── container/
│   └── Dockerfile
├── data/                    # SQLite DB (gitignored)
├── configs/                 # Claude configs (gitignored)
├── scripts/
│   ├── setup.sh
│   └── build-container.sh
├── tests/
│   ├── test_api.py
│   └── test_container.py
├── docs/
│   └── ...
├── SPEC.md                  # This file
└── README.md
```

---

## Open Questions

### 1. API Response Schema

**Question:** Should the API return Claude Code's raw JSON output or transform it into a normalized schema?

**Options:**
- **Pass-through**: Return Claude's JSON directly with additional metadata (simpler, less work)
- **Normalized**: Transform to our own schema (more control, potential breaking changes if Claude changes)
- **Both**: Support `?format=raw` or `?format=normalized` query parameter

**Recommendation:** Start with pass-through + metadata wrapper, add normalization later if needed.

### 2. Workspace Inheritance

**Question:** When spawning a child instance with `workspace_mode: inherit`, should it:
- Share the same workspace volume (concurrent access issues?)
- Create a copy-on-write snapshot
- Use MinIO to sync changes back to parent

**Recommendation:** Default to snapshot (copy), with option to sync changes back via explicit API call.

### 3. WebSocket vs Redis Pub/Sub for Client Streaming

**Current Design:** Gateway subscribes to Redis, forwards to WebSocket.

**Alternative:** Clients subscribe directly to Redis (requires Redis exposure, but lower latency).

**Recommendation:** Keep Redis internal, gateway relays via WebSocket for security.

### 4. MCP Server Integration

**Question:** Should the wrapper expose an MCP server for Claude to call, or use a different mechanism for spawning?

**Recommendation:** MCP is the most natural integration point - Claude already understands MCP tools.

---

## Reference Projects

These projects were analyzed during research:

| Project | Stars | Key Learnings |
|---------|-------|---------------|
| [e2b-dev/claude-code-fastapi](https://github.com/e2b-dev/claude-code-fastapi) | 15 | FastAPI + E2B sandbox pattern, session management |
| [textcortex/claude-code-sandbox](https://github.com/textcortex/claude-code-sandbox) | 258 | Docker + `--dangerously-skip-permissions`, web UI |
| [claude-did-this/claude-hub](https://github.com/claude-did-this/claude-hub) | 328 | Webhook API, async sessions, GitHub integration |
| [RchGrav/claudebox](https://github.com/RchGrav/claudebox) | 802 | Docker profiles, network firewall, MCP support |
| [parcadei/Continuous-Claude-v3](https://github.com/parcadei/Continuous-Claude-v3) | 3.2k | Context management, hooks, ledgers |
| [vijaythecoder/awesome-claude-agents](https://github.com/vijaythecoder/awesome-claude-agents) | 3.7k | Sub-agent team orchestration |
| [ruvnet/claude-flow](https://github.com/ruvnet/claude-flow) | 12k | Multi-agent swarms, consensus algorithms |
| [wshobson/agents](https://github.com/wshobson/agents) | 25.6k | Plugin architecture, 100+ agents |
| [Mng-dev-ai/claudex](https://github.com/Mng-dev-ai/claudex) | 158 | Local Docker sandbox, multi-provider |
| [ericc-ch/copilot-api](https://github.com/ericc-ch/copilot-api) | 2k | API proxy patterns |

---

## Next Steps

1. **Phase 1: Core Infrastructure**
   - [ ] Set up Docker Compose stack (gateway, redis, minio)
   - [ ] Implement basic FastAPI gateway
   - [ ] Build container image with Claude Code + wrapper
   - [ ] Implement session CRUD operations
   - [ ] Basic chat endpoint (synchronous)

2. **Phase 2: Streaming & Real-time**
   - [ ] WebSocket streaming implementation
   - [ ] Redis pub/sub integration
   - [ ] Real-time output forwarding

3. **Phase 3: Orchestration**
   - [ ] Child instance spawning
   - [ ] MCP tool for spawning
   - [ ] Result callback/pub-sub flow

4. **Phase 4: Production Readiness**
   - [ ] Workspace persistence (MinIO integration)
   - [ ] Prometheus metrics
   - [ ] Structured logging
   - [ ] Error handling & recovery
   - [ ] Documentation

---

*Last Updated: January 15, 2025*
*Version: 1.0.0-draft*
