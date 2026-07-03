"""Tests for Phase 56 — Fleet Management."""

import json
from unittest.mock import patch, MagicMock

import pytest

from tokenade.core.integration.fleet import (
    FleetManager,
    FleetSession,
    FleetReport,
)


# ─── FleetSession Tests ─────────────────────────────────────

class TestFleetSession:
    def test_defaults(self):
        s = FleetSession(
            name="gh", container_id="abc123",
            container_name="tokenade-gh", platform="docker",
        )
        assert s.status == "unknown"
        assert s.health_score == 0.0
        assert s.cookie_count == 0
        assert s.error == ""

    def test_running_session(self):
        s = FleetSession(
            name="gh", container_id="abc123",
            container_name="tokenade-gh", platform="docker",
            status="running", health_score=95.0,
            cookie_count=10, expired_cookies=1,
            auth_status="logged_in", site_name="github",
        )
        assert s.status == "running"
        assert s.health_score == 95.0


# ─── FleetReport Tests ─────────────────────────────────────

class TestFleetReport:
    def test_empty_report(self):
        r = FleetReport()
        assert r.total == 0
        assert r.healthy == 0
        assert r.unhealthy == 0
        assert r.stopped == 0
        assert r.errored == 0

    def test_counts_with_sessions(self):
        r = FleetReport(sessions=[
            FleetSession("a", "1", "c1", "docker", status="running"),
            FleetSession("b", "2", "c2", "docker", status="unhealthy"),
            FleetSession("c", "3", "c3", "docker", status="stopped"),
            FleetSession("d", "4", "c4", "docker", status="error"),
        ])
        assert r.total == 4
        assert r.healthy == 1
        assert r.unhealthy == 1
        assert r.stopped == 1
        assert r.errored == 1

    def test_to_table_empty(self):
        r = FleetReport()
        table = r.to_table()
        assert "No tokenade containers" in table

    def test_to_table_with_sessions(self):
        r = FleetReport(sessions=[
            FleetSession(
                "gh", "abc", "tokenade-gh", "docker",
                status="running", health_score=90.0,
                cookie_count=10, site_name="github",
            ),
        ])
        table = r.to_table()
        assert "TOKENADE FLEET STATUS" in table
        assert "tokenade-gh" in table
        assert "github" in table

    def test_to_json_empty(self):
        r = FleetReport()
        j = json.loads(r.to_json())
        assert j["total"] == 0
        assert j["sessions"] == []

    def test_to_json_with_sessions(self):
        r = FleetReport(sessions=[
            FleetSession(
                "gh", "abc", "tokenade-gh", "docker",
                status="running", health_score=90.0,
                cookie_count=10,
            ),
        ])
        j = json.loads(r.to_json())
        assert j["total"] == 1
        assert j["sessions"][0]["name"] == "gh"
        assert j["sessions"][0]["status"] == "running"


# ─── FleetManager Tests ─────────────────────────────────────

class TestFleetManager:
    def test_init(self):
        m = FleetManager()
        assert m.image_filter == "tokenade"

    def test_custom_image_filter(self):
        m = FleetManager(image_filter="my-tokenade")
        assert m.image_filter == "my-tokenade"

    @patch("subprocess.run")
    def test_check_docker_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        m = FleetManager()
        assert m._check_docker() is True

    @patch("subprocess.run")
    def test_check_docker_not_available(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        m = FleetManager()
        assert m._check_docker() is False

    @patch("subprocess.run")
    def test_check_kubectl_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        m = FleetManager()
        assert m._check_kubectl() is True

    @patch("subprocess.run")
    def test_check_kubectl_not_available(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        m = FleetManager()
        assert m._check_kubectl() is False

    @patch("subprocess.run")
    def test_discover_docker_by_label(self, mock_run):
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "label=tokenade" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="abc123\ttokenade-gh\ttokenade:latest\tUp 2 hours\t0.0.0.0:9222->9222/tcp",
                )
            return MagicMock(returncode=0, stdout="")
        mock_run.side_effect = side_effect
        m = FleetManager()
        containers = m._discover_docker_containers()
        assert len(containers) == 1
        assert containers[0]["name"] == "tokenade-gh"

    @patch("subprocess.run")
    def test_discover_docker_by_image_fallback(self, mock_run):
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "label=tokenade" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if cmd[0:3] == ["docker", "ps", "--format"]:
                return MagicMock(
                    returncode=0,
                    stdout="abc123\ttokenade-gh\ttokenade:latest\tUp 2 hours\t0.0.0.0:9222->9222/tcp",
                )
            return MagicMock(returncode=0, stdout="")
        mock_run.side_effect = side_effect
        m = FleetManager()
        containers = m._discover_docker_containers()
        assert len(containers) == 1

    @patch("subprocess.run")
    def test_status_no_docker_no_kubectl(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        m = FleetManager()
        report = m.status()
        assert report.total == 0
        assert report.docker_available is False
        assert report.kubectl_available is False

    @patch("subprocess.run")
    def test_status_with_docker_container(self, mock_run):
        def side_effect(cmd, **kwargs):
            # docker info
            if cmd == ["docker", "info"]:
                return MagicMock(returncode=0)
            # docker ps with label
            if "label=tokenade" in str(cmd):
                return MagicMock(
                    returncode=0,
                    stdout="abc123\ttokenade-gh\ttokenade:latest\tUp 2 hours\t",
                )
            # docker exec tokenade sessions list --json
            if "exec" in cmd and "sessions" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps([{
                        "name": "github",
                        "site": "github",
                        "cookies": 10,
                        "auth_status": "logged_in",
                    }]),
                )
            # kubectl version
            if cmd[0] == "kubectl":
                raise FileNotFoundError()
            return MagicMock(returncode=0, stdout="")
        mock_run.side_effect = side_effect
        m = FleetManager()
        report = m.status()
        assert report.total == 1
        assert report.sessions[0].name == "github"
        assert report.sessions[0].platform == "docker"

    @patch("subprocess.run")
    def test_status_stopped_container(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd == ["docker", "info"]:
                return MagicMock(returncode=0)
            if "label=tokenade" in str(cmd):
                return MagicMock(
                    returncode=0,
                    stdout="abc123\ttokenade-gh\ttokenade:latest\tExited (0) 5 minutes ago\t",
                )
            if cmd[0] == "kubectl":
                raise FileNotFoundError()
            return MagicMock(returncode=0, stdout="")
        mock_run.side_effect = side_effect
        m = FleetManager()
        report = m.status()
        assert report.total == 1
        assert report.sessions[0].status == "stopped"

    @patch("subprocess.run")
    def test_health_with_healthy_container(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd == ["docker", "info"]:
                return MagicMock(returncode=0)
            if "label=tokenade" in str(cmd):
                return MagicMock(
                    returncode=0,
                    stdout="abc123\ttokenade-gh\ttokenade:latest\tUp 2 hours\t",
                )
            if "exec" in cmd and "sessions" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps([{
                        "name": "github",
                        "site": "github",
                        "cookies": 10,
                        "auth_status": "logged_in",
                    }]),
                )
            if "exec" in cmd and "health" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "health_score": 0.95,
                        "expired_cookies": 0,
                        "issues": [],
                    }),
                )
            if cmd[0] == "kubectl":
                raise FileNotFoundError()
            return MagicMock(returncode=0, stdout="")
        mock_run.side_effect = side_effect
        m = FleetManager()
        report = m.health()
        assert report.total == 1
        assert report.sessions[0].health_score == 95.0

    @patch("subprocess.run")
    def test_health_with_unhealthy_container(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd == ["docker", "info"]:
                return MagicMock(returncode=0)
            if "label=tokenade" in str(cmd):
                return MagicMock(
                    returncode=0,
                    stdout="abc123\ttokenade-gh\ttokenade:latest\tUp 2 hours\t",
                )
            if "exec" in cmd and "sessions" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps([{
                        "name": "github",
                        "site": "github",
                        "cookies": 10,
                        "auth_status": "session_expired",
                    }]),
                )
            if "exec" in cmd and "health" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "health_score": 0.30,
                        "expired_cookies": 8,
                        "issues": ["8 expired cookies", "Auth status: session_expired"],
                    }),
                )
            if cmd[0] == "kubectl":
                raise FileNotFoundError()
            return MagicMock(returncode=0, stdout="")
        mock_run.side_effect = side_effect
        m = FleetManager()
        report = m.health()
        assert report.total == 1
        assert report.sessions[0].status == "unhealthy"
        assert report.sessions[0].health_score == 30.0

    @patch("subprocess.run")
    def test_refresh_all(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd == ["docker", "info"]:
                return MagicMock(returncode=0)
            if "label=tokenade" in str(cmd):
                return MagicMock(
                    returncode=0,
                    stdout="abc123\ttokenade-gh\ttokenade:latest\tUp 2 hours\t",
                )
            if "exec" in cmd and "refresh-browser" in cmd:
                return MagicMock(returncode=0, stdout="Refreshed successfully")
            return MagicMock(returncode=0, stdout="")
        mock_run.side_effect = side_effect
        m = FleetManager()
        results = m.refresh_all()
        assert len(results) == 1
        assert results[0]["success"] is True

    @patch("subprocess.run")
    def test_logs(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="line1\nline2\nline3\n"
        )
        m = FleetManager()
        output = m.logs("tokenade-gh", lines=3)
        assert "line1" in output
        assert "line3" in output

    @patch("subprocess.run")
    def test_discover_k8s_pods(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd[0] == "kubectl" and "get" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "items": [{
                            "metadata": {"name": "tokenade-gh-abc", "uid": "uid123"},
                            "status": {"phase": "Running"},
                        }],
                    }),
                )
            return MagicMock(returncode=0, stdout="")
        mock_run.side_effect = side_effect
        m = FleetManager()
        pods = m._discover_k8s_pods()
        assert len(pods) == 1
        assert pods[0]["name"] == "tokenade-gh-abc"


# ─── CLI Parser Tests ──────────────────────────────────────

class TestFleetCLIParser:
    def test_fleet_status_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["fleet", "status"])
        assert a.fleet_action == "status"

    def test_fleet_health_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["fleet", "health"])
        assert a.fleet_action == "health"

    def test_fleet_refresh_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["fleet", "refresh"])
        assert a.fleet_action == "refresh"

    def test_fleet_logs_parser(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["fleet", "logs", "my-container", "-n", "100"])
        assert a.fleet_action == "logs"
        assert a.container == "my-container"
        assert a.lines == 100

    def test_fleet_status_json(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        a = p.parse_args(["fleet", "status", "--format", "json"])
        assert a.format == "json"

    def test_fleet_help(self):
        from tokenade.cli import _build_parser
        p = _build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["fleet", "--help"])
