"""
Container orchestration for Tokenade — manages session refresh inside containers,
health monitoring with auto-restart, and session distribution across containers.
"""
import json
import logging
import subprocess
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ContainerHealth:
    """Health status of a container."""
    name: str
    container_id: str
    healthy: bool
    status: str  # running, stopped, unhealthy, starting
    restart_count: int = 0
    last_check: float = 0.0
    last_restart: float = 0.0
    error: Optional[str] = None


@dataclass
class SessionDistribution:
    """Maps sessions to containers for round-robin distribution."""
    container_name: str
    container_port: int
    session_files: List[str] = field(default_factory=list)


class ContainerOrchestrator:
    """High-level orchestrator for containerized Tokenade sessions.

    Handles:
    - Session refresh inside running containers via docker exec
    - Health monitoring with auto-restart
    - Session distribution across multiple containers
    """

    def __init__(self, image_name: str = "tokenade"):
        self.image_name = image_name
        self._health_history: Dict[str, List[ContainerHealth]] = {}
        self._stop_event = threading.Event()

    def refresh_session_in_container(
        self,
        container_name: str,
        session_path: str,
        target_url: Optional[str] = None,
        wait: int = 8,
    ) -> Dict[str, Any]:
        """Refresh a session inside a running container via docker exec.

        Returns:
            Dict with success, output, and any errors
        """
        cmd = ["docker", "exec", container_name, "tokenade", "refresh-browser",
               "--session", session_path, "--headless", "--wait", str(wait)]
        if target_url:
            cmd.extend(["--url", target_url])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=wait + 30,
            )
            success = result.returncode == 0
            return {
                "success": success,
                "container": container_name,
                "session": session_path,
                "output": result.stdout,
                "error": result.stderr if not success else None,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "container": container_name,
                "session": session_path,
                "output": "",
                "error": f"Timeout after {wait + 30}s",
            }
        except Exception as e:
            return {
                "success": False,
                "container": container_name,
                "session": session_path,
                "output": "",
                "error": str(e),
            }

    def refresh_all_in_container(
        self,
        container_name: str,
        sessions_dir: str = "/app/sessions",
    ) -> List[Dict[str, Any]]:
        """Refresh all sessions in a container.

        Returns:
            List of refresh results
        """
        # List session files in container
        result = subprocess.run(
            ["docker", "exec", container_name, "ls", sessions_dir],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return [{"success": False, "error": f"Failed to list sessions: {result.stderr}"}]

        files = [f for f in result.stdout.strip().split("\n") if f.endswith(".tokenade")]
        results = []
        for f in files:
            session_path = f"{sessions_dir}/{f}"
            r = self.refresh_session_in_container(container_name, session_path)
            results.append(r)
        return results

    def check_container_health(self, container_name: str) -> ContainerHealth:
        """Check health of a single container."""
        try:
            # Check if container is running
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return ContainerHealth(
                    name=container_name,
                    container_id="",
                    healthy=False,
                    status="not_found",
                    last_check=time.time(),
                    error="Container not found",
                )

            status = result.stdout.strip()

            # Get container ID
            id_result = subprocess.run(
                ["docker", "inspect", "--format", "{{.Id}}", container_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            container_id = id_result.stdout.strip()[:12] if id_result.returncode == 0 else ""

            # Get restart count
            restart_result = subprocess.run(
                ["docker", "inspect", "--format", "{{.RestartCount}}", container_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            restart_count = int(restart_result.stdout.strip()) if restart_result.returncode == 0 else 0

            # Try to connect to CDP port
            healthy = status == "running"
            error = None

            if healthy:
                # Try CDP health check
                port_result = subprocess.run(
                    ["docker", "inspect", "--format",
                     "{{range $p, $conf := .NetworkSettings.Ports}}{{$p}} {{end}}",
                     container_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # Just check if container is responsive
                exec_result = subprocess.run(
                    ["docker", "exec", container_name, "python", "-c", "print('ok')"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                healthy = exec_result.returncode == 0
                if not healthy:
                    error = "Container not responsive to exec"

            health = ContainerHealth(
                name=container_name,
                container_id=container_id,
                healthy=healthy,
                status=status,
                restart_count=restart_count,
                last_check=time.time(),
                error=error,
            )

            # Track history
            if container_name not in self._health_history:
                self._health_history[container_name] = []
            self._health_history[container_name].append(health)
            # Keep last 100 entries
            self._health_history[container_name] = self._health_history[container_name][-100:]

            return health

        except Exception as e:
            return ContainerHealth(
                name=container_name,
                container_id="",
                healthy=False,
                status="error",
                last_check=time.time(),
                error=str(e),
            )

    def check_all_health(self, prefix: str = "tokenade") -> List[ContainerHealth]:
        """Check health of all containers with given prefix."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}", "--filter", f"name={prefix}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []

            names = [n.strip() for n in result.stdout.strip().split("\n") if n.strip()]
            return [self.check_container_health(name) for name in names]
        except Exception as e:
            logger.error("Failed to check container health: %s", e)
            return []

    def restart_container(self, container_name: str, timeout: int = 30) -> bool:
        """Restart a container."""
        try:
            result = subprocess.run(
                ["docker", "restart", "-t", str(timeout), container_name],
                capture_output=True,
                text=True,
                timeout=timeout + 10,
            )
            if result.returncode == 0:
                logger.info("Restarted container %s", container_name)
                # Update history
                health = self.check_container_health(container_name)
                health.last_restart = time.time()
                return True
            return False
        except Exception as e:
            logger.error("Failed to restart %s: %s", container_name, e)
            return False

    def auto_restart_unhealthy(
        self,
        prefix: str = "tokenade",
        max_restarts: int = 3,
        check_interval: int = 60,
    ) -> None:
        """Monitor containers and auto-restart unhealthy ones.

        Runs until stop() is called.
        """
        self._stop_event.clear()
        restart_counts: Dict[str, int] = {}

        logger.info("Starting auto-restart monitor (interval=%ds)", check_interval)

        while not self._stop_event.is_set():
            health_list = self.check_all_health(prefix)
            for health in health_list:
                if not health.healthy and health.status == "running":
                    count = restart_counts.get(health.name, 0)
                    if count < max_restarts:
                        logger.warning(
                            "Container %s unhealthy, restarting (attempt %d/%d)",
                            health.name, count + 1, max_restarts,
                        )
                        if self.restart_container(health.name):
                            restart_counts[health.name] = count + 1
                    else:
                        logger.error(
                            "Container %s exceeded max restarts (%d), skipping",
                            health.name, max_restarts,
                        )
                elif health.healthy:
                    # Reset count on healthy
                    restart_counts.pop(health.name, None)

            self._stop_event.wait(check_interval)

        logger.info("Auto-restart monitor stopped")

    def stop(self):
        """Stop the auto-restart monitor."""
        self._stop_event.set()

    def distribute_sessions(
        self,
        session_files: List[str],
        container_names: List[str],
    ) -> List[SessionDistribution]:
        """Distribute sessions round-robin across containers.

        Returns:
            List of SessionDistribution mapping containers to sessions
        """
        if not container_names:
            return []

        distributions = [
            SessionDistribution(container_name=name, container_port=0)
            for name in container_names
        ]

        for i, session in enumerate(session_files):
            idx = i % len(distributions)
            distributions[idx].session_files.append(session)

        return distributions

    def get_health_history(self, container_name: str) -> List[ContainerHealth]:
        """Get health check history for a container."""
        return self._health_history.get(container_name, [])

    def get_status_summary(self, prefix: str = "tokenade") -> Dict[str, Any]:
        """Get summary status of all containers."""
        health_list = self.check_all_health(prefix)
        return {
            "total": len(health_list),
            "healthy": sum(1 for h in health_list if h.healthy),
            "unhealthy": sum(1 for h in health_list if not h.healthy and h.status == "running"),
            "stopped": sum(1 for h in health_list if h.status != "running"),
            "containers": [
                {
                    "name": h.name,
                    "status": h.status,
                    "healthy": h.healthy,
                    "restart_count": h.restart_count,
                    "error": h.error,
                }
                for h in health_list
            ],
        }


def generate_compose_override(
    sessions: List[str],
    base_port: int = 9222,
    restart_policy: str = "unless-stopped",
    health_check_interval: str = "30s",
) -> str:
    """Generate a docker-compose override YAML for session containers.

    Creates one service per session file with proper health checks,
    restart policies, and resource limits.
    """
    lines = [
        "version: '3.8'",
        "",
        "services:",
    ]

    for i, session in enumerate(sessions):
        service_name = f"tokenade-session-{i}"
        port = base_port + i
        session_name = Path(session).stem

        lines.extend([
            f"  {service_name}:",
            "    build: .",
            "    image: tokenade:latest",
            f"    container_name: {service_name}",
            f'    ports:',
            f'      - "{port}:9222"',
            "    volumes:",
            f"      - ./sessions/{Path(session).name}:/app/sessions/input.tokenade:ro",
            "      - tokenade-browser:/app/browser_data",
            "    environment:",
            "      - TOKENADE_DATA_DIR=/app",
            "      - PYTHONUNBUFFERED=1",
            "    cap_add:",
            "      - SYS_ADMIN",
            "    security_opt:",
            "      - seccomp=unconfined",
            f"    restart: {restart_policy}",
            "    healthcheck:",
            "      test: [\"CMD\", \"python\", \"-c\", \"import tokenade; print(tokenade.__version__)\"]",
            f"      interval: {health_check_interval}",
            "      timeout: 10s",
            "      retries: 3",
            "      start_period: 60s",
            "    deploy:",
            "      resources:",
            "        limits:",
            "          cpus: '1.0'",
            "          memory: 512M",
            "        reservations:",
            "          cpus: '0.25'",
            "          memory: 128M",
            "",
        ])

    lines.extend([
        "",
        "volumes:",
        "  tokenade-browser:",
    ])

    return "\n".join(lines) + "\n"


def generate_dockerfile_multiarch() -> str:
    """Generate a Dockerfile with multi-arch build support (docker buildx).

    This is a reference Dockerfile that works with:
        docker buildx build --platform linux/amd64,linux/arm64 -t tokenade:latest .
    """
    return """# Tokenade - Multi-arch production image
# Build with: docker buildx build --platform linux/amd64,linux/arm64 -t tokenade:latest .

FROM --platform=$BUILDPLATFORM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    gcc \\
    libffi-dev \\
    libssl-dev \\
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY tokenade/ ./tokenade/

# Install tokenade package
RUN pip install --no-cache-dir --user .

# Stage 2: Runtime image
FROM python:3.12-slim

LABEL maintainer="Tokenade Team"
LABEL description="Production-grade session portability tool"

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    libglib2.0-0 \\
    libnss3 \\
    libnspr4 \\
    libatk1.0-0 \\
    libatk-bridge2.0-0 \\
    libcups2 \\
    libdrm2 \\
    libdbus-1-3 \\
    libxcb1 \\
    libxkbcommon0 \\
    libx11-6 \\
    libxcomposite1 \\
    libxdamage1 \\
    libxext6 \\
    libxfixes3 \\
    libxrandr2 \\
    libgbm1 \\
    libpango-1.0-0 \\
    libcairo2 \\
    libasound2 \\
    libatspi2.0-0 \\
    xvfb \\
    libsecret-1-0 \\
    curl \\
    jq \\
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Install Playwright browsers
RUN playwright install chromium && playwright install-deps chromium

# Create non-root user
RUN groupadd -r tokenade && useradd -r -g tokenade -d /app -s /bin/bash tokenade

# Create data directories
RUN mkdir -p /app/sessions /app/browser_data /app/.fingerprints /app/reports \\
    && chown -R tokenade:tokenade /app

USER tokenade

ENV PYTHONUNBUFFERED=1
ENV TOKENADE_DATA_DIR=/app
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \\
    CMD python -c "import tokenade; print(tokenade.__version__)" || exit 1

EXPOSE 9222
EXPOSE 9224

ENTRYPOINT ["tokenade"]
CMD ["--help"]
"""
