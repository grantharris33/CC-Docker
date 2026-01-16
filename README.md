# CC-Docker (Claude Code Docker)

A Docker-based service that wraps Claude Code with a FastAPI server, providing an API for external applications to control and interact with Claude Code instances.

## Features

- **REST + WebSocket API**: Programmatic access to Claude Code
- **Container Isolation**: Each session runs in its own Docker container
- **Session Management**: Multi-turn conversations with persistence
- **Streaming Output**: Real-time JSON streaming via WebSocket
- **Recursive Orchestration**: Claude Code instances can spawn child instances
- **Workspace Management**: Optional persistence of project workspaces

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
│   └── requirements.txt
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

## Development

### Local Development

```bash
cd gateway
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run gateway locally
JWT_SECRET=test-secret uvicorn app.main:app --reload
```

### Running Tests

```bash
pip install -r tests/requirements.txt
pytest tests/
```

## License

MIT License
