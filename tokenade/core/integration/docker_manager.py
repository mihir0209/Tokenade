"""
Docker session management for Tokenade.
"""
import subprocess
import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DockerContainer:
    """Docker container info."""
    id: str
    name: str
    image: str
    status: str
    ports: str
    created: str


class DockerSessionManager:
    """Manage Tokenade sessions in Docker containers."""

    def __init__(self, image_name: str = "tokenade", network: str = "tokenade-net"):
        self.image_name = image_name
        self.network = network
        self._docker_available = self._check_docker()

    def _check_docker(self) -> bool:
        """Check if Docker is available."""
        try:
            subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def is_available(self) -> bool:
        """Check if Docker is available."""
        return self._docker_available

    def create_session_container(
        self,
        session_file: str,
        name: str,
        port: int = 9222,
        detach: bool = True,
    ) -> Optional[str]:
        """Create and start a container serving a session file.

        Returns container ID or None on failure.
        """
        if not self._docker_available:
            logger.error("Docker is not available")
            return None

        session_path = os.path.abspath(session_file)
        if not os.path.isfile(session_path):
            logger.error("Session file not found: %s", session_path)
            return None

        cmd = [
            "docker", "run",
        ]
        if detach:
            cmd.append("-d")
        cmd.extend([
            "--name", name,
            "-p", f"{port}:9222",
            "-v", f"{session_path}:/app/sessions/input.tokenade:ro",
        ])
        cmd.extend([self.image_name, "proxy", "--host", "0.0.0.0", "--port", "9222"])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            container_id = result.stdout.strip()
            logger.info("Created container %s (id=%s)", name, container_id[:12])
            return container_id
        except subprocess.CalledProcessError as e:
            logger.error("Failed to create container %s: %s", name, e.stderr)
            return None
        except subprocess.TimeoutExpired:
            logger.error("Timeout creating container %s", name)
            return None

    def list_containers(self, all_containers: bool = False) -> List[DockerContainer]:
        """List Tokenade containers."""
        if not self._docker_available:
            return []

        cmd = [
            "docker", "ps",
            "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.CreatedAt}}",
        ]
        if all_containers:
            cmd.append("-a")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            containers = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 6:
                    containers.append(DockerContainer(
                        id=parts[0],
                        name=parts[1],
                        image=parts[2],
                        status=parts[3],
                        ports=parts[4],
                        created=parts[5],
                    ))
            return containers
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Failed to list containers: %s", e)
            return []

    def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """Stop a running container."""
        if not self._docker_available:
            return False

        try:
            subprocess.run(
                ["docker", "stop", "-t", str(timeout), container_id],
                capture_output=True,
                check=True,
                timeout=timeout + 5,
            )
            logger.info("Stopped container %s", container_id[:12])
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Failed to stop container %s: %s", container_id[:12], e)
            return False

    def remove_container(self, container_id: str, force: bool = False) -> bool:
        """Remove a container."""
        if not self._docker_available:
            return False

        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(container_id)

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                check=True,
                timeout=10,
            )
            logger.info("Removed container %s", container_id[:12])
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Failed to remove container %s: %s", container_id[:12], e)
            return False

    def get_container_logs(self, container_id: str, tail: int = 100) -> str:
        """Get container logs."""
        if not self._docker_available:
            return ""

        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(tail), container_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout + result.stderr
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Failed to get logs for %s: %s", container_id[:12], e)
            return ""

    def exec_in_container(self, container_id: str, command: List[str]) -> str:
        """Execute command in running container."""
        if not self._docker_available:
            return ""

        cmd = ["docker", "exec", container_id] + command

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Failed to exec in %s: %s", container_id[:12], e)
            return ""

    def build_image(self, tag: Optional[str] = None, dockerfile: str = "Dockerfile") -> bool:
        """Build Docker image from Dockerfile."""
        if not self._docker_available:
            return False

        image_tag = tag or self.image_name
        cmd = [
            "docker", "build",
            "-t", image_tag,
            "-f", dockerfile,
            ".",
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            )
            logger.info("Built image %s", image_tag)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Failed to build image %s: %s", image_tag, e)
            return False

    def pull_image(self, tag: str = "latest") -> bool:
        """Pull image from registry."""
        if not self._docker_available:
            return False

        image_ref = f"{self.image_name}:{tag}"

        try:
            subprocess.run(
                ["docker", "pull", image_ref],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            logger.info("Pulled image %s", image_ref)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Failed to pull image %s: %s", image_ref, e)
            return False

    def create_network(self) -> bool:
        """Create Docker network for Tokenade containers."""
        if not self._docker_available:
            return False

        try:
            subprocess.run(
                ["docker", "network", "create", self.network],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            logger.info("Created network %s", self.network)
            return True
        except subprocess.CalledProcessError as e:
            if "already exists" in (e.stderr or ""):
                logger.debug("Network %s already exists", self.network)
                return True
            logger.error("Failed to create network %s: %s", self.network, e.stderr)
            return False

    def run_batch(self, session_files: List[str], prefix: str = "tokenade") -> List[Dict]:
        """Start multiple session containers.

        Returns list of {container_id, name, port, status}.
        """
        results = []
        for i, session_file in enumerate(session_files):
            name = f"{prefix}-{i}"
            container_id = self.create_session_container(
                session_file=session_file,
                name=name,
                port=9222 + i,
            )
            results.append({
                "container_id": container_id or "",
                "name": name,
                "port": 9222 + i,
                "status": "running" if container_id else "failed",
            })
        return results

    def cleanup(self, remove_all: bool = False) -> int:
        """Stop and optionally remove all Tokenade containers. Returns count cleaned."""
        containers = self.list_containers(all_containers=True)
        count = 0
        for container in containers:
            if not container.name.startswith("tokenade"):
                continue
            if "Up" in container.status:
                self.stop_container(container.id)
            if remove_all:
                self.remove_container(container.id, force=True)
            count += 1
        return count

    def get_status(self) -> Dict:
        """Get overall status: docker available, containers running, network exists."""
        status: Dict = {
            "docker_available": self._docker_available,
            "containers_running": 0,
            "network_exists": False,
        }

        if not self._docker_available:
            return status

        containers = self.list_containers(all_containers=False)
        status["containers_running"] = sum(
            1 for c in containers if c.name.startswith("tokenade")
        )

        try:
            result = subprocess.run(
                ["docker", "network", "inspect", self.network],
                capture_output=True,
                text=True,
                timeout=5,
            )
            status["network_exists"] = result.returncode == 0
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            status["network_exists"] = False

        return status
