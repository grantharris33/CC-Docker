# CC-Docker (Claude Code Docker)

A Docker-based service that wraps Claude Code with a FastAPI server, providing an API for external applications to control and interact with Claude Code instances.

## Features

- **REST + WebSocket API**: Programmatic access to Claude Code
- **Container Isolation**: Each session runs in its own Docker container
- **Session Management**: Multi-turn conversations with persistence
- **Streaming Output**: Real-time JSON streaming via WebSocket
- **Recursive Orchestration**: Claude Code instances can spawn child instances
- **Workspace Management**: Optional persistence of project workspaces
- **Discord Integration**: Human-in-the-loop notifications and interactive questions
- **MCP Server Support**: Pre-configured tools for GitHub, databases, filesystem, and more

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+
- Node.js 20+ (for building container image)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/your-repo/cc-docker.git
cd cc-docker
```

2. Copy and configure environment:
```bash
cp .env.example .env
# Edit .env with your settings
```

3. Run the setup script:
```bash
./scripts/setup.sh
```

Or manually:
```bash
# Build the Claude Code container image
./scripts/build-container.sh

# Start services
docker-compose up -d
```

4. Access the API:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- MinIO Console: http://localhost:9001

## API Overview

### Authentication

All API endpoints require a JWT token:
```
Authorization: Bearer <jwt_token>
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/sessions | Create a new session |
| GET | /api/v1/sessions | List all sessions |
| GET | /api/v1/sessions/{id} | Get session details |
| POST | /api/v1/sessions/{id}/stop | Stop a session |
| DELETE | /api/v1/sessions/{id} | Delete a session |
| POST | /api/v1/sessions/{id}/chat | Send a message |
| WS | /api/v1/sessions/{id}/stream | WebSocket streaming |
| POST | /api/v1/sessions/{id}/spawn | Spawn child instance |
| POST | /api/v1/discord/notify | Send Discord notification |
| POST | /api/v1/discord/ask | Ask user question via Discord |

### Example: Create Session

```bash
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace": {"type": "ephemeral"},
    "config": {"model": "opus-4"}
  }'
```

### Example: Send Message

```bash
curl -X POST http://localhost:8000/api/v1/sessions/{session_id}/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, Claude!", "stream": true}'
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose Stack                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌─────────┐   ┌─────────┐              │
│  │   FastAPI   │   │  Redis  │   │  MinIO  │              │
│  │   Gateway   │◄─►│(pub/sub)│   │(storage)│              │
│  └──────┬──────┘   └─────────┘   └─────────┘              │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────┐               │
│  │        Claude Code Containers           │               │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐   │               │
│  │  │Session 1│ │Session 2│ │Session N│   │               │
│  │  └─────────┘ └─────────┘ └─────────┘   │               │
│  └─────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
cc-docker/
├── gateway/             # FastAPI gateway service
│   ├── app/
│   │   ├── api/        # REST and WebSocket endpoints
│   │   ├── core/       # Config, security, dependencies
│   │   ├── db/         # Database models and connection
│   │   ├── models/     # Pydantic schemas
│   │   └── services/   # Business logic
│   ├── Dockerfile
│   └── pyproject.toml
├── wrapper/             # Claude Code wrapper (runs in container)
├── container/           # Container image Dockerfile
├── scripts/             # Setup and build scripts
├── tests/               # Test suite
├── docker-compose.yml
├── SPEC.md              # Full technical specification
└── README.md
```

## Configuration

Environment variables (set in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| JWT_SECRET | - | Secret key for JWT tokens |
| MINIO_ACCESS_KEY | minioadmin | MinIO access key |
| MINIO_SECRET_KEY | minioadmin | MinIO secret key |
| LOG_LEVEL | INFO | Logging level |
| CONTAINER_TIMEOUT_DEFAULT | 3600 | Default session timeout |
| MAX_SPAWN_DEPTH | 5 | Maximum child spawn depth |
| DISCORD_BOT_TOKEN | - | Discord bot token (optional) |
| DISCORD_CHANNEL_ID | - | Discord channel ID for notifications (optional) |
| DISCORD_QUESTION_TIMEOUT | 1800 | Default timeout for Discord questions (seconds) |
| DISCORD_MAX_RETRIES | 3 | Maximum retry attempts for Discord questions |

### Discord Integration

CC-Docker can communicate with users via Discord for notifications and interactive questions. To enable:

1. **Create a Discord bot** (see `docs/DISCORD_SETUP.md`)
2. **Set environment variables** in `.env`:
   ```bash
   DISCORD_BOT_TOKEN=your_bot_token_here
   DISCORD_CHANNEL_ID=your_channel_id_here
   ```
3. **Use from Claude Code sessions** via MCP tools:
   ```javascript
   // Send notification
   notify_user({
     message: "Task completed successfully!",
     priority: "normal"
   });

   // Ask question and wait for response
   const response = await ask_user({
     question: "Should I proceed with deployment?",
     timeout_seconds: 300
   });
   ```

For detailed setup instructions, see [`docs/DISCORD_SETUP.md`](docs/DISCORD_SETUP.md) and [`DISCORD_TEST_RESULTS.md`](DISCORD_TEST_RESULTS.md).

## Development

### Local Development

```bash
cd gateway

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run gateway locally
JWT_SECRET=test-secret uv run uvicorn app.main:app --reload
```

### Running Tests

```bash
uv sync --dev
uv run pytest tests/
```

### Adding Dependencies

```bash
# Add a runtime dependency
uv add <package-name>

# Add a dev dependency
uv add --dev <package-name>
```

## License

MIT License
