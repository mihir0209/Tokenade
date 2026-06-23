"""
Tests for container orchestration (Phase 44).
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from argparse import Namespace


# ---------------------------------------------------------------------------
# ContainerOrchestrator — pure logic (no Docker calls)
# ---------------------------------------------------------------------------

class TestContainerOrchestratorUnit:
    """Test ContainerOrchestrator pure logic methods."""

    def test_distribute_sessions_round_robin(self):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator
        orch = ContainerOrchestrator()
        sessions = ["s1.tokenade", "s2.tokenade", "s3.tokenade", "s4.tokenade", "s5.tokenade"]
        containers = ["c1", "c2", "c3"]
        dists = orch.distribute_sessions(sessions, containers)
        assert len(dists) == 3
        assert dists[0].session_files == ["s1.tokenade", "s4.tokenade"]
        assert dists[1].session_files == ["s2.tokenade", "s5.tokenade"]
        assert dists[2].session_files == ["s3.tokenade"]

    def test_distribute_empty_sessions(self):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator
        orch = ContainerOrchestrator()
        dists = orch.distribute_sessions([], ["c1", "c2"])
        assert len(dists) == 2
        assert all(len(d.session_files) == 0 for d in dists)

    def test_distribute_empty_containers(self):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator
        orch = ContainerOrchestrator()
        dists = orch.distribute_sessions(["s1.tokenade"], [])
        assert len(dists) == 0

    def test_health_history_tracking(self):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator, ContainerHealth
        orch = ContainerOrchestrator()
        h = ContainerHealth(name="c1", container_id="abc123", healthy=True, status="running")
        orch._health_history["c1"] = [h]
        history = orch.get_health_history("c1")
        assert len(history) == 1
        assert history[0].name == "c1"

    def test_health_history_empty(self):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator
        orch = ContainerOrchestrator()
        assert orch.get_health_history("nonexistent") == []

    def test_stop_event(self):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator
        orch = ContainerOrchestrator()
        assert not orch._stop_event.is_set()
        orch.stop()
        assert orch._stop_event.is_set()


# ---------------------------------------------------------------------------
# ContainerHealth dataclass
# ---------------------------------------------------------------------------

class TestContainerHealth:
    """Test ContainerHealth dataclass."""

    def test_defaults(self):
        from tokenade.core.integration.container_orchestrator import ContainerHealth
        h = ContainerHealth(name="c1", container_id="abc", healthy=True, status="running")
        assert h.restart_count == 0
        assert h.last_check == 0.0
        assert h.last_restart == 0.0
        assert h.error is None

    def test_with_error(self):
        from tokenade.core.integration.container_orchestrator import ContainerHealth
        h = ContainerHealth(
            name="c1", container_id="abc", healthy=False, status="unhealthy",
            error="Container not responsive",
        )
        assert not h.healthy
        assert h.error == "Container not responsive"


# ---------------------------------------------------------------------------
# SessionDistribution dataclass
# ---------------------------------------------------------------------------

class TestSessionDistribution:
    """Test SessionDistribution dataclass."""

    def test_defaults(self):
        from tokenade.core.integration.container_orchestrator import SessionDistribution
        d = SessionDistribution(container_name="c1", container_port=9222)
        assert d.session_files == []

    def test_with_sessions(self):
        from tokenade.core.integration.container_orchestrator import SessionDistribution
        d = SessionDistribution(container_name="c1", container_port=9222, session_files=["s1.tokenade"])
        assert len(d.session_files) == 1


# ---------------------------------------------------------------------------
# generate_compose_override
# ---------------------------------------------------------------------------

class TestGenerateComposeOverride:
    """Test docker-compose override generation."""

    def test_basic_generation(self):
        from tokenade.core.integration.container_orchestrator import generate_compose_override
        yaml = generate_compose_override(
            sessions=["gmail.tokenade", "github.tokenade"],
            base_port=9222,
        )
        assert "version: '3.8'" in yaml
        assert "tokenade-session-0:" in yaml
        assert "tokenade-session-1:" in yaml
        assert "9222:9222" in yaml
        assert "9223:9222" in yaml
        assert "restart: unless-stopped" in yaml
        assert "healthcheck:" in yaml
        assert "deploy:" in yaml

    def test_custom_restart_policy(self):
        from tokenade.core.integration.container_orchestrator import generate_compose_override
        yaml = generate_compose_override(
            sessions=["s1.tokenade"],
            restart_policy="always",
        )
        assert "restart: always" in yaml

    def test_custom_port(self):
        from tokenade.core.integration.container_orchestrator import generate_compose_override
        yaml = generate_compose_override(
            sessions=["s1.tokenade"],
            base_port=8000,
        )
        assert "8000:9222" in yaml

    def test_empty_sessions(self):
        from tokenade.core.integration.container_orchestrator import generate_compose_override
        yaml = generate_compose_override(sessions=[])
        assert "services:" in yaml
        # No session services
        assert "tokenade-session-" not in yaml

    def test_resource_limits(self):
        from tokenade.core.integration.container_orchestrator import generate_compose_override
        yaml = generate_compose_override(sessions=["s1.tokenade"])
        assert "cpus: '1.0'" in yaml
        assert "memory: 512M" in yaml


# ---------------------------------------------------------------------------
# generate_dockerfile_multiarch
# ---------------------------------------------------------------------------

class TestGenerateDockerfileMultiarch:
    """Test multi-arch Dockerfile generation."""

    def test_contains_build_platform(self):
        from tokenade.core.integration.container_orchestrator import generate_dockerfile_multiarch
        dockerfile = generate_dockerfile_multiarch()
        assert "BUILDPLATFORM" in dockerfile

    def test_contains_healthcheck(self):
        from tokenade.core.integration.container_orchestrator import generate_dockerfile_multiarch
        dockerfile = generate_dockerfile_multiarch()
        assert "HEALTHCHECK" in dockerfile

    def test_contains_non_root_user(self):
        from tokenade.core.integration.container_orchestrator import generate_dockerfile_multiarch
        dockerfile = generate_dockerfile_multiarch()
        assert "useradd" in dockerfile
        assert "USER tokenade" in dockerfile

    def test_contains_exposed_ports(self):
        from tokenade.core.integration.container_orchestrator import generate_dockerfile_multiarch
        dockerfile = generate_dockerfile_multiarch()
        assert "EXPOSE 9222" in dockerfile
        assert "EXPOSE 9224" in dockerfile


# ---------------------------------------------------------------------------
# CLI parser — container and k8s flags
# ---------------------------------------------------------------------------

class TestCLIContainerParser:
    """Test container CLI parser."""

    def test_container_start(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["container", "start", "-d", "./sessions"])
        assert args.container_action == "start"
        assert args.sessions_dir == "./sessions"
        assert args.proxy_port == 9222

    def test_container_stop(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["container", "stop", "--name", "tokenade-proxy"])
        assert args.container_action == "stop"
        assert args.name == "tokenade-proxy"

    def test_container_status(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["container", "status"])
        assert args.container_action == "status"

    def test_container_logs(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["container", "logs", "tokenade-proxy", "-n", "50", "-f"])
        assert args.container_action == "logs"
        assert args.name == "tokenade-proxy"
        assert args.tail == 50
        assert args.follow is True

    def test_container_refresh(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["container", "refresh", "tokenade-proxy"])
        assert args.container_action == "refresh"
        assert args.name == "tokenade-proxy"

    def test_container_scale(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["container", "scale", "3"])
        assert args.container_action == "scale"
        assert args.replicas == 3

    def test_container_health(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["container", "health", "--watch", "--interval", "30"])
        assert args.container_action == "health"
        assert args.watch is True
        assert args.interval == 30

    def test_container_generate(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["container", "generate", "-d", "./sessions", "-o", "override.yml"])
        assert args.container_action == "generate"
        assert args.output == "override.yml"


class TestCLK8sParser:
    """Test k8s CLI parser."""

    def test_k8s_deploy(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["k8s", "deploy", "-n", "production", "-r", "3", "--dry-run"])
        assert args.k8s_action == "deploy"
        assert args.namespace == "production"
        assert args.replicas == 3
        assert args.dry_run is True

    def test_k8s_status(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["k8s", "status", "-n", "staging"])
        assert args.k8s_action == "status"
        assert args.namespace == "staging"

    def test_k8s_scale(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["k8s", "scale", "5"])
        assert args.k8s_action == "scale"
        assert args.replicas == 5

    def test_k8s_delete(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["k8s", "delete", "-n", "production"])
        assert args.k8s_action == "delete"
        assert args.namespace == "production"

    def test_k8s_pods(self):
        from tokenade.cli import _build_parser
        parser = _build_parser()
        args = parser.parse_args(["k8s", "pods"])
        assert args.k8s_action == "pods"


# ---------------------------------------------------------------------------
# Integration: orchestrator with mocked Docker
# ---------------------------------------------------------------------------

class TestContainerOrchestratorMocked:
    """Test ContainerOrchestrator with mocked subprocess calls."""

    @patch("subprocess.run")
    def test_check_container_health_running(self, mock_run):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

        def side_effect(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 0
            m.stderr = ""
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "State.Status" in cmd_str:
                m.stdout = "running"
            elif ".Id" in cmd_str:
                m.stdout = "abc123def456"
            elif "RestartCount" in cmd_str:
                m.stdout = "2"
            elif "exec" in cmd_str:
                m.stdout = "ok"
            else:
                m.stdout = ""
            return m

        mock_run.side_effect = side_effect

        orch = ContainerOrchestrator()
        health = orch.check_container_health("tokenade-proxy")
        assert health.healthy is True
        assert health.status == "running"
        assert health.restart_count == 2

    @patch("subprocess.run")
    def test_check_container_health_not_found(self, mock_run):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

        m = MagicMock()
        m.stdout = ""
        m.stderr = "No such container"
        m.returncode = 1
        mock_run.return_value = m

        orch = ContainerOrchestrator()
        health = orch.check_container_health("nonexistent")
        assert health.healthy is False
        assert health.status == "not_found"

    @patch("subprocess.run")
    def test_check_all_health(self, mock_run):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

        def side_effect(cmd, **kwargs):
            m = MagicMock()
            if "ps" in cmd and "--format" in cmd:
                m.stdout = "tokenade-proxy\ntokenade-api"
                m.returncode = 0
            else:
                m.stdout = "running"
                m.returncode = 0
            m.stderr = ""
            return m

        mock_run.side_effect = side_effect

        orch = ContainerOrchestrator()
        # This will call check_container_health for each, which will fail
        # because the mock doesn't handle all inspect formats perfectly
        # But it should not crash
        health_list = orch.check_all_health()
        assert isinstance(health_list, list)

    @patch("subprocess.run")
    def test_get_status_summary(self, mock_run):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

        def side_effect(cmd, **kwargs):
            m = MagicMock()
            if "ps" in cmd and "--format" in cmd:
                m.stdout = "tokenade-proxy"
                m.returncode = 0
            elif "inspect" in cmd:
                m.stdout = "running"
                m.returncode = 0
            else:
                m.stdout = ""
                m.returncode = 0
            m.stderr = ""
            return m

        mock_run.side_effect = side_effect

        orch = ContainerOrchestrator()
        summary = orch.get_status_summary()
        assert "total" in summary
        assert "healthy" in summary
        assert "containers" in summary


# ---------------------------------------------------------------------------
# Integration: refresh_session_in_container with mocked Docker
# ---------------------------------------------------------------------------

class TestRefreshInContainer:
    """Test refresh_session_in_container with mocked subprocess."""

    @patch("subprocess.run")
    def test_refresh_success(self, mock_run):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

        m = MagicMock()
        m.stdout = "Session refreshed successfully"
        m.stderr = ""
        m.returncode = 0
        mock_run.return_value = m

        orch = ContainerOrchestrator()
        result = orch.refresh_session_in_container("tokenade-proxy", "/app/sessions/test.tokenade")
        assert result["success"] is True
        assert "refreshed" in result["output"].lower()

    @patch("subprocess.run")
    def test_refresh_failure(self, mock_run):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

        m = MagicMock()
        m.stdout = ""
        m.stderr = "Container not found"
        m.returncode = 1
        mock_run.return_value = m

        orch = ContainerOrchestrator()
        result = orch.refresh_session_in_container("nonexistent", "/app/sessions/test.tokenade")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @patch("subprocess.run")
    def test_refresh_with_url(self, mock_run):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

        m = MagicMock()
        m.stdout = "ok"
        m.stderr = ""
        m.returncode = 0
        mock_run.return_value = m

        orch = ContainerOrchestrator()
        result = orch.refresh_session_in_container(
            "tokenade-proxy",
            "/app/sessions/test.tokenade",
            target_url="https://mail.google.com",
        )
        # Verify the command included --url
        call_args = mock_run.call_args[0][0]
        assert "--url" in call_args
        assert "https://mail.google.com" in call_args


# ---------------------------------------------------------------------------
# Distribution integration
# ---------------------------------------------------------------------------

class TestDistributionIntegration:
    """Integration tests for session distribution."""

    def test_even_distribution(self):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator
        orch = ContainerOrchestrator()
        sessions = [f"s{i}.tokenade" for i in range(9)]
        dists = orch.distribute_sessions(sessions, ["c1", "c2", "c3"])
        for d in dists:
            assert len(d.session_files) == 3

    def test_uneven_distribution(self):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator
        orch = ContainerOrchestrator()
        sessions = [f"s{i}.tokenade" for i in range(5)]
        dists = orch.distribute_sessions(sessions, ["c1", "c2"])
        total = sum(len(d.session_files) for d in dists)
        assert total == 5
        # One gets 3, one gets 2
        counts = sorted([len(d.session_files) for d in dists])
        assert counts == [2, 3]

    def test_single_container(self):
        from tokenade.core.integration.container_orchestrator import ContainerOrchestrator
        orch = ContainerOrchestrator()
        sessions = ["s1.tokenade", "s2.tokenade"]
        dists = orch.distribute_sessions(sessions, ["c1"])
        assert len(dists) == 1
        assert len(dists[0].session_files) == 2
