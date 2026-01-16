"""Pytest fixtures for CC-Docker tests."""

import asyncio
import os
import sys
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add gateway to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gateway"))

from app.core.config import Settings, get_settings
from app.core.security import create_token
from app.db.database import Base, engine, init_db
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings() -> Settings:
    """Override settings for testing."""
    return Settings(
        database_url="sqlite+aiosqlite:///./test.db",
        redis_url="redis://localhost:6379",
        minio_url="http://localhost:9000",
        jwt_secret="test-secret",
        debug=True,
    )


@pytest_asyncio.fixture
async def test_db():
    """Set up test database."""
    await init_db()
    yield
    # Clean up
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> dict:
    """Create authorization headers with a valid test token."""
    token = create_token("test-user")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def api_base_url() -> str:
    """Base URL for API endpoints."""
    return "/api/v1"
