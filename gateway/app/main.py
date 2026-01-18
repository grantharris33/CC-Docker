"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from prometheus_client import make_asgi_app

from app.api.routes import chat, discord, health, sessions, spawn, tasks
from app.api.websocket import stream, vnc
from app.core.config import get_settings
from app.core.security import create_token
from app.db.database import init_db, get_db
from app.services.container import container_manager
from app.services.discord import start_discord_bot, stop_discord_bot
from app.services.scheduler import SchedulerService

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting CC-Docker Gateway...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start Discord bot
    redis_client = redis.from_url(settings.redis_url, decode_responses=False)
    await start_discord_bot(redis_client)
    logger.info("Discord bot initialized")

    # Start task scheduler
    scheduler = SchedulerService()
    await scheduler.start()
    logger.info("Task scheduler started")

    # Load all enabled task schedules from database
    async for db in get_db():
        try:
            await scheduler.reload_all_schedules(db)
            logger.info("Task schedules loaded")
        finally:
            break

    # Store scheduler in app state for access in routes
    app.state.scheduler = scheduler

    yield

    # Shutdown
    logger.info("Shutting down CC-Docker Gateway...")
    await scheduler.shutdown()
    await stop_discord_bot()
    await container_manager.close()
    await redis_client.aclose()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Docker-based service for Claude Code API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Include routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(
    sessions.router, prefix="/api/v1/sessions", tags=["Sessions"]
)
app.include_router(
    chat.router, prefix="/api/v1/sessions", tags=["Chat"]
)
app.include_router(
    spawn.router, prefix="/api/v1/sessions", tags=["Spawn"]
)
app.include_router(
    stream.router, prefix="/api/v1/sessions", tags=["WebSocket"]
)
app.include_router(
    vnc.router, prefix="/api/v1/sessions", tags=["VNC"]
)
app.include_router(
    discord.router, prefix="/api/v1/discord", tags=["Discord"]
)
app.include_router(
    tasks.router, prefix="/api/v1/tasks", tags=["Tasks"]
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
    }


@app.get("/api/v1")
async def api_info():
    """API information endpoint."""
    return {
        "version": "v1",
        "endpoints": {
            "sessions": "/api/v1/sessions",
            "tasks": "/api/v1/tasks",
            "discord": "/api/v1/discord",
            "health": "/health",
            "metrics": "/metrics",
        },
    }


# Serve test UI
STATIC_DIR = Path(__file__).parent.parent / "static"


@app.get("/test")
async def test_ui():
    """Serve the test UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/v1/test-token")
async def get_test_token(user_id: str = "test-user"):
    """Generate a test JWT token for the test UI. DO NOT use in production."""
    token = create_token(user_id, expires_in=86400)  # 24 hours
    return {"token": token, "user_id": user_id}


# Mount static files (for any additional assets)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
