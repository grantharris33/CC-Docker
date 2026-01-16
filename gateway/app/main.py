"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.routes import chat, health, sessions, spawn
from app.api.websocket import stream
from app.core.config import get_settings
from app.db.database import init_db
from app.services.container import container_manager

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

    yield

    # Shutdown
    logger.info("Shutting down CC-Docker Gateway...")
    await container_manager.close()


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
            "health": "/health",
            "metrics": "/metrics",
        },
    }
