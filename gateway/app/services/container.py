"""Container management service using aiodocker."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import aiodocker

from app.core.config import get_settings
from app.models.container import ContainerInfo, ContainerStatus

logger = logging.getLogger(__name__)
settings = get_settings()


class ContainerManager:
    """Manages Docker containers for Claude Code sessions."""

    def __init__(self):
        self._docker: Optional[aiodocker.Docker] = None

    async def _get_docker(self) -> aiodocker.Docker:
        """Get or create Docker client."""
        if self._docker is None:
            self._docker = aiodocker.Docker()
        return self._docker

    async def close(self) -> None:
        """Close Docker client."""
        if self._docker:
            await self._docker.close()
            self._docker = None

    async def create_container(
        self,
        session_id: str,
        workspace_path: str,
        environment: Dict[str, str],
        claude_config_path: Optional[str] = None,
    ) -> ContainerInfo:
        """Create a new container for a Claude Code session."""
        docker = await self._get_docker()

        # Build container configuration
        config = {
            "Image": settings.container_image,
            "Env": [f"{k}={v}" for k, v in environment.items()],
            "Labels": {
                "cc-docker.session_id": session_id,
                "cc-docker.created_at": datetime.utcnow().isoformat(),
            },
            "HostConfig": {
                "Binds": [
                    f"{workspace_path}:/workspace",
                ],
                "NetworkMode": settings.container_network,
                "Memory": self._parse_memory(settings.container_memory_limit),
                "MemoryReservation": self._parse_memory(
                    settings.container_memory_reservation
                ),
                "NanoCpus": int(float(settings.container_cpu_limit) * 1e9),
            },
        }

        # Add Claude config mount if available
        if claude_config_path:
            config["HostConfig"]["Binds"].append(
                f"{claude_config_path}:/root/.claude:ro"
            )

        logger.info(f"Creating container for session {session_id}")

        try:
            container = await docker.containers.create(
                config=config,
                name=f"cc-docker-{session_id}",
            )

            return ContainerInfo(
                container_id=container.id,
                status=ContainerStatus.CREATING,
                session_id=session_id,
                created_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(f"Failed to create container: {e}")
            raise

    async def start_container(self, container_id: str) -> None:
        """Start a container."""
        docker = await self._get_docker()
        container = await docker.containers.get(container_id)
        await container.start()
        logger.info(f"Started container {container_id}")

    async def stop_container(self, container_id: str, timeout: int = 10) -> None:
        """Stop a container gracefully."""
        docker = await self._get_docker()
        try:
            container = await docker.containers.get(container_id)
            await container.stop(t=timeout)
            logger.info(f"Stopped container {container_id}")
        except aiodocker.exceptions.DockerError as e:
            if "404" in str(e):
                logger.warning(f"Container {container_id} not found")
            else:
                raise

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        """Remove a container."""
        docker = await self._get_docker()
        try:
            container = await docker.containers.get(container_id)
            await container.delete(force=force)
            logger.info(f"Removed container {container_id}")
        except aiodocker.exceptions.DockerError as e:
            if "404" in str(e):
                logger.warning(f"Container {container_id} not found")
            else:
                raise

    async def get_container_status(self, container_id: str) -> ContainerStatus:
        """Get container status."""
        docker = await self._get_docker()
        try:
            container = await docker.containers.get(container_id)
            info = await container.show()
            state = info["State"]["Status"]

            status_map = {
                "created": ContainerStatus.CREATING,
                "running": ContainerStatus.RUNNING,
                "paused": ContainerStatus.RUNNING,
                "restarting": ContainerStatus.RUNNING,
                "exited": ContainerStatus.STOPPED,
                "dead": ContainerStatus.FAILED,
            }
            return status_map.get(state, ContainerStatus.FAILED)
        except aiodocker.exceptions.DockerError:
            return ContainerStatus.FAILED

    async def get_container_logs(
        self, container_id: str, tail: int = 100
    ) -> str:
        """Get container logs."""
        docker = await self._get_docker()
        try:
            container = await docker.containers.get(container_id)
            logs = await container.log(stdout=True, stderr=True, tail=tail)
            return "".join(logs)
        except aiodocker.exceptions.DockerError:
            return ""

    async def exec_in_container(
        self, container_id: str, cmd: list[str]
    ) -> tuple[int, str]:
        """Execute a command in a running container."""
        docker = await self._get_docker()
        container = await docker.containers.get(container_id)

        exec_obj = await container.exec(cmd, stdout=True, stderr=True)
        stream = exec_obj.start()
        output = []

        async with stream:
            while True:
                msg = await stream.read_out()
                if msg is None:
                    break
                output.append(msg.data.decode())

        inspect = await exec_obj.inspect()
        return inspect["ExitCode"], "".join(output)

    async def list_session_containers(self) -> list[ContainerInfo]:
        """List all cc-docker containers."""
        docker = await self._get_docker()
        containers = await docker.containers.list(
            filters={"label": ["cc-docker.session_id"]}
        )

        result = []
        for container in containers:
            info = await container.show()
            result.append(
                ContainerInfo(
                    container_id=container.id,
                    status=await self.get_container_status(container.id),
                    session_id=info["Config"]["Labels"]["cc-docker.session_id"],
                    created_at=datetime.fromisoformat(
                        info["Created"].replace("Z", "+00:00")
                    ),
                )
            )
        return result

    async def wait_for_startup(
        self, container_id: str, timeout: int = None
    ) -> bool:
        """Wait for container to start."""
        timeout = timeout or settings.startup_timeout
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            status = await self.get_container_status(container_id)
            if status == ContainerStatus.RUNNING:
                return True
            if status == ContainerStatus.FAILED:
                return False
            await asyncio.sleep(0.5)

        return False

    @staticmethod
    def _parse_memory(memory_str: str) -> int:
        """Parse memory string to bytes."""
        memory_str = memory_str.lower()
        multipliers = {"k": 1024, "m": 1024**2, "g": 1024**3}
        for suffix, mult in multipliers.items():
            if memory_str.endswith(suffix):
                return int(float(memory_str[:-1]) * mult)
        return int(memory_str)


# Singleton instance
container_manager = ContainerManager()


async def get_container_manager() -> ContainerManager:
    """Dependency for getting container manager."""
    return container_manager
