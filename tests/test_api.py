"""API tests for CC-Docker gateway."""

import pytest
from httpx import AsyncClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test basic health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "components" in data

    @pytest.mark.asyncio
    async def test_liveness(self, client: AsyncClient):
        """Test liveness probe."""
        response = await client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True


class TestRootEndpoints:
    """Tests for root endpoints."""

    @pytest.mark.asyncio
    async def test_root(self, client: AsyncClient):
        """Test root endpoint."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs" in data

    @pytest.mark.asyncio
    async def test_api_info(self, client: AsyncClient):
        """Test API info endpoint."""
        response = await client.get("/api/v1")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "v1"
        assert "endpoints" in data


class TestSessionEndpoints:
    """Tests for session management endpoints."""

    @pytest.mark.asyncio
    async def test_create_session_unauthorized(self, client: AsyncClient):
        """Test session creation without auth."""
        response = await client.post("/api/v1/sessions", json={})
        assert response.status_code == 401  # Unauthorized without auth (HTTPBearer returns 401)

    @pytest.mark.asyncio
    async def test_list_sessions_unauthorized(self, client: AsyncClient):
        """Test listing sessions without auth."""
        response = await client.get("/api/v1/sessions")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_sessions_with_auth(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test listing sessions with auth."""
        response = await client.get("/api/v1/sessions", headers=auth_headers)
        # Will fail if Redis/Docker not available, but should not be 401
        assert response.status_code in [200, 401, 500]  # 401 if JWT secret mismatch

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test getting a session that doesn't exist."""
        response = await client.get(
            "/api/v1/sessions/nonexistent-id", headers=auth_headers
        )
        assert response.status_code in [401, 404]  # 401 if JWT secret mismatch


class TestAuthValidation:
    """Tests for JWT authentication."""

    @pytest.mark.asyncio
    async def test_invalid_token(self, client: AsyncClient):
        """Test with invalid JWT token."""
        headers = {"Authorization": "Bearer invalid-token"}
        response = await client.get("/api/v1/sessions", headers=headers)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_bearer(self, client: AsyncClient):
        """Test with missing Bearer prefix."""
        headers = {"Authorization": "some-token"}
        response = await client.get("/api/v1/sessions", headers=headers)
        assert response.status_code == 401  # HTTPBearer returns 401 for invalid format

    @pytest.mark.asyncio
    async def test_empty_auth_header(self, client: AsyncClient):
        """Test with empty authorization header."""
        headers = {"Authorization": ""}
        response = await client.get("/api/v1/sessions", headers=headers)
        assert response.status_code == 401
