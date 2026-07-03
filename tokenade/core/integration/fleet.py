"""
Fleet Management — unified view of sessions across Docker/k8s containers.

Read-only coordinator that queries running containers on demand.
No server process — just CLI commands that aggregate data.

Usage:
    fleet = FleetManager()
    report = fleet.status()
    print(report.to_table())
"""

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


@dataclass
class FleetSession:
    """A session discovered in a container or pod."""
    name: str
    container_id: str
    container_name: str
    platform: str  # "docker" | "kubernetes"
    status: str = "unknown"  # running | stopped | unhealthy | error
    health_score: float = 0.0
    cookie_count: int = 0
    expired_cookies: int = 0
    auth_status: str = "unknown"
    site_name: str = "unknown"
    last_refresh: str = ""
    proxy_url: str = ""
    error: str = ""


@dataclass
class FleetReport:
    """Aggregated fleet status."""
    sessions: List[FleetSession] = field(default_factory=list)
    scan_duration_ms: float = 0.0
    docker_available: bool = False
    kubectl_available: bool = False

    @property
    def total(self) -> int:
        return len(self.sessions)

    @property
    def healthy(self) -> int:
        return sum(1 for s in self.sessions if s.status == "running")

    @property
    def unhealthy(self) -> int:
        return sum(1 for s in self.sessions if s.status == "unhealthy")

    @property
    def stopped(self) -> int:
        return sum(1 for s in self.sessions if s.status == "stopped")

    @property
    def errored(self) -> int:
        return sum(1 for s in self.sessions if s.status == "error")

    def to_table(self) -> str:
        """Render as a colored terminal table."""
        if not self.sessions:
            return (
                "No tokenade containers found.\n\n"
                "Start one with:\n"
                "  tokenade container start -s <session> --port 9222\n"
                "  tokenade k8s deploy -s <session>"
            )

        lines = [
            "=" * 70,
            "TOKENADE FLEET STATUS",
            "=" * 70,
            f"Containers: {self.total} | "
            f"Running: {self.healthy} | "
            f"Unhealthy: {self.unhealthy} | "
            f"Stopped: {self.stopped} | "
            f"Errors: {self.errored}",
            f"Scan time: {self.scan_duration_ms:.0f}ms",
            "-" * 70,
            "",
        ]

        # Table header
        header = (
            f"  {'NAME':<20} {'PLATFORM':<10} {'STATUS':<10} "
            f"{'HEALTH':<8} {'COOKIES':<8} {'EXPIRED':<8} {'SITE':<12}"
        )
        lines.append(header)
        lines.append("  " + "-" * 68)

        for s in self.sessions:
            icon = {
                "running": "🟢",
                "stopped": "🔴",
                "unhealthy": "🟡",
                "error": "💥",
            }.get(s.status, "⚪")

            health_str = f"{s.health_score:.0f}%" if s.health_score > 0 else "—"
            lines.append(
                f"  {icon} {s.container_name:<18} {s.platform:<10} "
                f"{s.status:<10} {health_str:<8} {s.cookie_count:<8} "
                f"{s.expired_cookies:<8} {s.site_name:<12}"
            )
            if s.error:
                lines.append(f"      Error: {s.error}")

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_json(self) -> str:
        """Render as JSON."""
        data = {
            "total": self.total,
            "healthy": self.healthy,
            "unhealthy": self.unhealthy,
            "stopped": self.stopped,
            "errored": self.errored,
            "scan_duration_ms": self.scan_duration_ms,
            "sessions": [],
        }
        for s in self.sessions:
            data["sessions"].append({
                "name": s.name,
                "container_id": s.container_id,
                "container_name": s.container_name,
                "platform": s.platform,
                "status": s.status,
                "health_score": s.health_score,
                "cookie_count": s.cookie_count,
                "expired_cookies": s.expired_cookies,
                "auth_status": s.auth_status,
                "site_name": s.site_name,
                "proxy_url": s.proxy_url,
                "error": s.error,
            })
        return json.dumps(data, indent=2)


class FleetManager:
    """Queries Docker/k8s containers for session status.

    Read-only — does not create, stop, or modify containers.
    """

    def __init__(self, image_filter: str = "tokenade"):
        self.image_filter = image_filter

    def _check_docker(self) -> bool:
        try:
            r = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5
            )
            return r.returncode == 0
        except Exception:
            return False

    def _check_kubectl(self) -> bool:
        try:
            r = subprocess.run(
                ["kubectl", "version", "--client"],
                capture_output=True, timeout=5,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _discover_docker_containers(self) -> List[Dict[str, str]]:
        """Find running containers with tokenade label or image."""
        containers = []

        # First: try label-based discovery
        try:
            r = subprocess.run(
                [
                    "docker", "ps",
                    "--filter", "label=tokenade=true",
                    "--format",
                    "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                for line in r.stdout.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        containers.append({
                            "id": parts[0],
                            "name": parts[1],
                            "image": parts[2],
                            "status": parts[3],
                            "ports": parts[4] if len(parts) > 4 else "",
                        })
        except Exception:
            pass

        # Fallback: image-based discovery
        if not containers:
            try:
                r = subprocess.run(
                    [
                        "docker", "ps",
                        "--format",
                        "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}",
                    ],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0 and r.stdout.strip():
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split("\t")
                        if len(parts) >= 4 and self.image_filter in parts[2]:
                            containers.append({
                                "id": parts[0],
                                "name": parts[1],
                                "image": parts[2],
                                "status": parts[3],
                                "ports": parts[4] if len(parts) > 4 else "",
                            })
            except Exception:
                pass

        return containers

    def _query_sessions_in_container(
        self, container_id: str
    ) -> List[Dict[str, Any]]:
        """Run tokenade sessions list --json inside a container."""
        try:
            r = subprocess.run(
                [
                    "docker", "exec", container_id,
                    "tokenade", "sessions", "list", "--json",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
        except Exception:
            pass
        return []

    def _query_health_in_container(
        self, container_id: str, session_name: str
    ) -> Dict[str, Any]:
        """Run tokenade health -s <session> --json inside a container."""
        try:
            r = subprocess.run(
                [
                    "docker", "exec", container_id,
                    "tokenade", "health", "-s", session_name, "--json",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
        except Exception:
            pass
        return {}

    def _discover_k8s_pods(self) -> List[Dict[str, str]]:
        """Find pods with app=tokenade label."""
        pods = []
        try:
            r = subprocess.run(
                [
                    "kubectl", "get", "pods",
                    "-l", "app=tokenade",
                    "-o", "json",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout)
                for item in data.get("items", []):
                    name = item["metadata"]["name"]
                    phase = item["status"].get("phase", "Unknown")
                    uid = item["metadata"].get("uid", "")
                    pods.append({
                        "id": uid,
                        "name": name,
                        "status": phase,
                    })
        except Exception:
            pass
        return pods

    def _query_sessions_in_pod(
        self, pod_name: str, namespace: str = "default"
    ) -> List[Dict[str, Any]]:
        """Run tokenade sessions list --json inside a pod."""
        try:
            r = subprocess.run(
                [
                    "kubectl", "exec", pod_name,
                    "-n", namespace,
                    "--", "tokenade", "sessions", "list", "--json",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
        except Exception:
            pass
        return []

    def status(self) -> FleetReport:
        """Scan all containers/pods and return fleet status."""
        start = time.time()
        report = FleetReport()
        report.docker_available = self._check_docker()
        report.kubectl_available = self._check_kubectl()

        # Scan Docker containers
        if report.docker_available:
            containers = self._discover_docker_containers()
            for c in containers:
                is_running = "Up" in c.get("status", "")
                container_status = "running" if is_running else "stopped"

                # Query sessions inside container
                sessions_data = []
                if is_running:
                    sessions_data = self._query_sessions_in_container(c["id"])

                if sessions_data:
                    for s in sessions_data:
                        report.sessions.append(FleetSession(
                            name=s.get("name", "unknown"),
                            container_id=c["id"][:12],
                            container_name=c["name"],
                            platform="docker",
                            status=container_status,
                            cookie_count=s.get("cookies", 0),
                            auth_status=s.get("auth_status", "unknown"),
                            site_name=s.get("site", "unknown"),
                        ))
                else:
                    # Container exists but no session data
                    report.sessions.append(FleetSession(
                        name="(no sessions)",
                        container_id=c["id"][:12],
                        container_name=c["name"],
                        platform="docker",
                        status=container_status,
                        error="No session data available" if is_running else "",
                    ))

        # Scan k8s pods
        if report.kubectl_available:
            pods = self._discover_k8s_pods()
            for p in pods:
                is_running = p["status"] == "Running"
                pod_status = "running" if is_running else "stopped"

                sessions_data = []
                if is_running:
                    sessions_data = self._query_sessions_in_pod(p["name"])

                if sessions_data:
                    for s in sessions_data:
                        report.sessions.append(FleetSession(
                            name=s.get("name", "unknown"),
                            container_id=p["id"][:12],
                            container_name=p["name"],
                            platform="kubernetes",
                            status=pod_status,
                            cookie_count=s.get("cookies", 0),
                            auth_status=s.get("auth_status", "unknown"),
                            site_name=s.get("site", "unknown"),
                        ))
                else:
                    report.sessions.append(FleetSession(
                        name="(no sessions)",
                        container_id=p["id"][:12],
                        container_name=p["name"],
                        platform="kubernetes",
                        status=pod_status,
                    ))

        report.scan_duration_ms = (time.time() - start) * 1000
        return report

    def health(self) -> FleetReport:
        """Like status() but also runs health checks in each container."""
        report = self.status()

        for session in report.sessions:
            if session.status != "running":
                continue
            if session.name == "(no sessions)":
                continue

            if session.platform == "docker":
                h = self._query_health_in_container(
                    session.container_id, session.name
                )
                if h:
                    session.health_score = h.get("health_score", 0) * 100
                    session.expired_cookies = h.get("expired_cookies", 0)
                    issues = h.get("issues", [])
                    if issues:
                        session.status = "unhealthy"
                        session.error = "; ".join(issues[:3])
                    else:
                        session.status = "running"

        return report

    def refresh_all(self) -> List[Dict[str, Any]]:
        """Trigger refresh in all running containers."""
        results = []
        containers = self._discover_docker_containers()

        for c in containers:
            if "Up" not in c.get("status", ""):
                continue

            try:
                r = subprocess.run(
                    [
                        "docker", "exec", c["id"],
                        "tokenade", "refresh-browser",
                        "--headless", "--wait", "5",
                    ],
                    capture_output=True, text=True, timeout=60,
                )
                results.append({
                    "container": c["name"],
                    "success": r.returncode == 0,
                    "output": r.stdout[:500] if r.returncode == 0 else "",
                    "error": r.stderr[:500] if r.returncode != 0 else "",
                })
            except Exception as e:
                results.append({
                    "container": c["name"],
                    "success": False,
                    "error": str(e)[:500],
                })

        return results

    def logs(self, container_name: str, lines: int = 50) -> str:
        """Get logs from a specific container."""
        try:
            r = subprocess.run(
                ["docker", "logs", "--tail", str(lines), container_name],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return r.stdout
            return f"Error: {r.stderr}"
        except Exception as e:
            return f"Error: {e}"
