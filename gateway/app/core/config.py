"""Application configuration using Pydantic settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "CC-Docker Gateway"
    version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite:///data/cc-docker.db"

    # Redis
    redis_url: str = "redis://redis:6379"

    # MinIO
    minio_url: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "cc-docker"

    # JWT Authentication
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"

    # Docker
    docker_host: str = "unix:///var/run/docker.sock"
    container_image: str = "cc-docker-container:latest"
    container_network: str = "cc-docker_cc-internal"

    # Container Limits
    container_cpu_limit: str = "2"
    container_memory_limit: str = "4g"
    container_cpu_reservation: str = "0.5"
    container_memory_reservation: str = "512m"

    # Timeouts
    startup_timeout: int = 60
    idle_timeout: int = 300
    session_timeout: int = 3600
    request_timeout: int = 600

    # Limits
    max_sessions_per_user: int = 10
    max_spawn_depth: int = 5
    max_children_per_session: int = 10
    max_total_instances: int = 50

    # Claude Config
    claude_config_path: Optional[str] = None
    claude_credentials_path: Optional[str] = None

    # Secrets for MCP servers (injected into containers)
    cc_secret_github_token: Optional[str] = None
    cc_secret_postgres_url: Optional[str] = None
    cc_secret_sqlite_db_path: Optional[str] = None
    cc_secret_browser_proxy: Optional[str] = None

    # Default MCP servers to enable
    cc_default_mcp_servers: str = "cc-docker,filesystem,playwright,sqlite"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars not defined in Settings


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
