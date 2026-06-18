"""Tests for tokenade.core.integration.docker_manager"""
import subprocess
from unittest.mock import patch, MagicMock


from tokenade.core.integration.docker_manager import DockerContainer, DockerSessionManager


# ---------------------------------------------------------------------------
# DockerContainer
# ---------------------------------------------------------------------------

class TestDockerContainer:
    def test_creation(self):
        c = DockerContainer(
            id="abc123",
            name="mycontainer",
            image="nginx:latest",
            status="Up 2 hours",
            ports="0.0.0.0:8080->80/tcp",
            created="2024-01-01 00:00:00",
        )
        assert c.id == "abc123"
        assert c.name == "mycontainer"
        assert c.image == "nginx:latest"
        assert c.status == "Up 2 hours"
        assert c.ports == "0.0.0.0:8080->80/tcp"
        assert c.created == "2024-01-01 00:00:00"


# ---------------------------------------------------------------------------
# DockerSessionManager – availability
# ---------------------------------------------------------------------------

class TestDockerAvailability:
    @patch("subprocess.run")
    def test_available(self, mock_run):
        mock_run.return_value = MagicMock()
        mgr = DockerSessionManager()
        assert mgr.is_available() is True

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_unavailable_file_not_found(self, _mock):
        mgr = DockerSessionManager()
        assert mgr.is_available() is False

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker"))
    def test_unavailable_error(self, _mock):
        mgr = DockerSessionManager()
        assert mgr.is_available() is False

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 5))
    def test_unavailable_timeout(self, _mock):
        mgr = DockerSessionManager()
        assert mgr.is_available() is False

    def test_init_defaults(self):
        mgr = DockerSessionManager.__new__(DockerSessionManager)
        mgr._docker_available = False
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        assert mgr.image_name == "tokenade"
        assert mgr.network == "tokenade-net"

    def test_init_custom(self):
        mgr = DockerSessionManager.__new__(DockerSessionManager)
        mgr._docker_available = False
        mgr.image_name = "myimg"
        mgr.network = "mynet"
        assert mgr.image_name == "myimg"
        assert mgr.network == "mynet"


# ---------------------------------------------------------------------------
# create_session_container
# ---------------------------------------------------------------------------

class TestCreateSessionContainer:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.create_session_container("/tmp/f.json", "c1") is None

    def test_file_not_found(self, mgr=None):
        mgr = self._mgr(available=True)
        assert mgr.create_session_container("/nonexistent/file.json", "c1") is None

    @patch("subprocess.run")
    @patch("os.path.isfile", return_value=True)
    @patch("os.path.abspath", side_effect=lambda x: x)
    def test_success(self, _abs, _isfile, mock_run):
        mock_run.return_value = MagicMock(stdout="abc123def456\n", stderr="")
        mgr = self._mgr(available=True)
        cid = mgr.create_session_container("/tmp/session.json", "mycontainer", port=9333)
        assert cid == "abc123def456"
        cmd = mock_run.call_args[0][0]
        assert "docker" in cmd
        assert "run" in cmd
        assert "-d" in cmd
        assert "mycontainer" in cmd
        assert "9333:9222" in cmd

    @patch("subprocess.run")
    @patch("os.path.isfile", return_value=True)
    @patch("os.path.abspath", side_effect=lambda x: x)
    def test_no_detach(self, _abs, _isfile, mock_run):
        mock_run.return_value = MagicMock(stdout="abc123\n", stderr="")
        mgr = self._mgr(available=True)
        cid = mgr.create_session_container("/tmp/s.json", "c1", detach=False)
        cmd = mock_run.call_args[0][0]
        assert "-d" not in cmd
        assert cid == "abc123"

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker", stderr="error msg"))
    @patch("os.path.isfile", return_value=True)
    @patch("os.path.abspath", side_effect=lambda x: x)
    def test_create_error(self, _abs, _isfile, _mock):
        mgr = self._mgr(available=True)
        assert mgr.create_session_container("/tmp/s.json", "c1") is None

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 30))
    @patch("os.path.isfile", return_value=True)
    @patch("os.path.abspath", side_effect=lambda x: x)
    def test_timeout(self, _abs, _isfile, _mock):
        mgr = self._mgr(available=True)
        assert mgr.create_session_container("/tmp/s.json", "c1") is None


# ---------------------------------------------------------------------------
# list_containers
# ---------------------------------------------------------------------------

class TestListContainers:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.list_containers() == []

    @patch("subprocess.run")
    def test_success(self, mock_run):
        output = "abc123\ttok-0\ttokenade:latest\tUp 2 hours\t0.0.0.0:9222->9222/tcp\t2024-01-01"
        mock_run.return_value = MagicMock(stdout=output, stderr="")
        mgr = self._mgr(available=True)
        containers = mgr.list_containers()
        assert len(containers) == 1
        assert containers[0].id == "abc123"
        assert containers[0].name == "tok-0"

    @patch("subprocess.run")
    def test_all_containers_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mgr = self._mgr(available=True)
        mgr.list_containers(all_containers=True)
        cmd = mock_run.call_args[0][0]
        assert "-a" in cmd

    @patch("subprocess.run")
    def test_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.list_containers() == []

    @patch("subprocess.run")
    def test_partial_line_skipped(self, mock_run):
        mock_run.return_value = MagicMock(stdout="abc\ttok\timg\tUp\tport\n", stderr="")
        mgr = self._mgr(available=True)
        containers = mgr.list_containers()
        assert len(containers) == 0

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker"))
    def test_error(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.list_containers() == []


# ---------------------------------------------------------------------------
# stop_container
# ---------------------------------------------------------------------------

class TestStopContainer:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.stop_container("abc") is False

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.stop_container("abc123", timeout=15) is True
        cmd = mock_run.call_args[0][0]
        assert "docker" in cmd
        assert "stop" in cmd
        assert "abc123" in cmd

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker"))
    def test_failure(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.stop_container("abc123") is False

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 15))
    def test_timeout(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.stop_container("abc123") is False


# ---------------------------------------------------------------------------
# remove_container
# ---------------------------------------------------------------------------

class TestRemoveContainer:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.remove_container("abc") is False

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.remove_container("abc123") is True
        cmd = mock_run.call_args[0][0]
        assert "rm" in cmd
        assert "abc123" in cmd

    @patch("subprocess.run")
    def test_force(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.remove_container("abc123", force=True) is True
        cmd = mock_run.call_args[0][0]
        assert "-f" in cmd

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker"))
    def test_failure(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.remove_container("abc123") is False


# ---------------------------------------------------------------------------
# get_container_logs
# ---------------------------------------------------------------------------

class TestGetContainerLogs:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.get_container_logs("abc") == ""

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="line1\n", stderr="err1\n")
        mgr = self._mgr(available=True)
        logs = mgr.get_container_logs("abc123", tail=50)
        assert "line1" in logs
        assert "err1" in logs
        cmd = mock_run.call_args[0][0]
        assert "--tail" in cmd

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker"))
    def test_error(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.get_container_logs("abc") == ""

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 10))
    def test_timeout(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.get_container_logs("abc") == ""


# ---------------------------------------------------------------------------
# exec_in_container
# ---------------------------------------------------------------------------

class TestExecInContainer:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.exec_in_container("abc", ["ls"]) == ""

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="file1.txt\n", stderr="")
        mgr = self._mgr(available=True)
        output = mgr.exec_in_container("abc123", ["ls", "-la"])
        assert "file1.txt" in output
        cmd = mock_run.call_args[0][0]
        assert "exec" in cmd
        assert "abc123" in cmd

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker"))
    def test_error(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.exec_in_container("abc", ["cmd"]) == ""

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 30))
    def test_timeout(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.exec_in_container("abc", ["cmd"]) == ""


# ---------------------------------------------------------------------------
# build_image
# ---------------------------------------------------------------------------

class TestBuildImage:
    def _mgr(self, available=True, image_name="tokenade"):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = image_name
        mgr.network = "tokenade-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.build_image() is False

    @patch("subprocess.run")
    def test_success_default(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.build_image() is True
        cmd = mock_run.call_args[0][0]
        assert "build" in cmd
        assert "-t" in cmd
        assert "tokenade" in cmd
        assert "-f" in cmd
        assert "Dockerfile" in cmd

    @patch("subprocess.run")
    def test_success_custom_tag_and_dockerfile(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mgr = self._mgr(available=True, image_name="tokenade")
        assert mgr.build_image(tag="myimg:v2", dockerfile="Custom.Dockerfile") is True
        cmd = mock_run.call_args[0][0]
        assert "myimg:v2" in cmd
        assert "Custom.Dockerfile" in cmd

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker"))
    def test_failure(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.build_image() is False


# ---------------------------------------------------------------------------
# pull_image
# ---------------------------------------------------------------------------

class TestPullImage:
    def _mgr(self, available=True, image_name="tokenade"):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = image_name
        mgr.network = "tokenade-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.pull_image() is False

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.pull_image(tag="v1.0") is True
        cmd = mock_run.call_args[0][0]
        assert "pull" in cmd
        assert "tokenade:v1.0" in cmd

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "docker"))
    def test_failure(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.pull_image() is False

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 120))
    def test_timeout(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.pull_image() is False


# ---------------------------------------------------------------------------
# create_network
# ---------------------------------------------------------------------------

class TestCreateNetwork:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "my-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.create_network() is False

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.create_network() is True
        cmd = mock_run.call_args[0][0]
        assert "network" in cmd
        assert "create" in cmd
        assert "my-net" in cmd

    @patch("subprocess.run")
    def test_already_exists(self, mock_run):
        err = subprocess.CalledProcessError(1, "docker", stderr="network with name my-net already exists")
        mock_run.side_effect = err
        mgr = self._mgr(available=True)
        assert mgr.create_network() is True

    @patch("subprocess.run")
    def test_other_error(self, mock_run):
        err = subprocess.CalledProcessError(1, "docker", stderr="permission denied")
        mock_run.side_effect = err
        mgr = self._mgr(available=True)
        assert mgr.create_network() is False


# ---------------------------------------------------------------------------
# run_batch
# ---------------------------------------------------------------------------

class TestRunBatch:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        return mgr

    @patch.object(DockerSessionManager, "create_session_container")
    def test_batch(self, mock_create):
        mock_create.side_effect = ["id1", None, "id3"]
        mgr = self._mgr(available=True)
        results = mgr.run_batch(["f1.json", "f2.json", "f3.json"], prefix="test")
        assert len(results) == 3
        assert results[0]["container_id"] == "id1"
        assert results[0]["status"] == "running"
        assert results[0]["name"] == "test-0"
        assert results[0]["port"] == 9222
        assert results[1]["container_id"] == ""
        assert results[1]["status"] == "failed"
        assert results[1]["port"] == 9223
        assert results[2]["container_id"] == "id3"
        assert results[2]["status"] == "running"
        assert results[2]["port"] == 9224

    @patch.object(DockerSessionManager, "create_session_container", return_value=None)
    def test_batch_empty(self, _mock):
        mgr = self._mgr(available=True)
        results = mgr.run_batch([])
        assert results == []


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        return mgr

    @patch.object(DockerSessionManager, "list_containers")
    def test_cleanup_stop_only(self, mock_list):
        mock_list.return_value = [
            DockerContainer("id1", "tokenade-0", "img", "Up 1h", "", ""),
            DockerContainer("id2", "other-0", "img", "Up 1h", "", ""),
            DockerContainer("id3", "tokenade-1", "img", "Exited (0)", "", ""),
        ]
        mgr = self._mgr(available=True)
        with patch.object(mgr, "stop_container", return_value=True) as mock_stop, \
                patch.object(mgr, "remove_container", return_value=True) as mock_remove:
            count = mgr.cleanup(remove_all=False)
            assert count == 2  # only tokenade-0 and tokenade-1
            assert mock_stop.call_count == 1  # only the "Up" one
            assert mock_remove.call_count == 0

    @patch.object(DockerSessionManager, "list_containers")
    def test_cleanup_remove_all(self, mock_list):
        mock_list.return_value = [
            DockerContainer("id1", "tokenade-0", "img", "Up 1h", "", ""),
            DockerContainer("id2", "tokenade-1", "img", "Exited", "", ""),
        ]
        mgr = self._mgr(available=True)
        with patch.object(mgr, "stop_container", return_value=True), \
                patch.object(mgr, "remove_container", return_value=True) as mock_remove:
            count = mgr.cleanup(remove_all=True)
            assert count == 2
            assert mock_remove.call_count == 2

    @patch.object(DockerSessionManager, "list_containers", return_value=[])
    def test_cleanup_no_containers(self, _mock):
        mgr = self._mgr(available=True)
        count = mgr.cleanup()
        assert count == 0


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def _mgr(self, available=True):
        mgr = object.__new__(DockerSessionManager)
        mgr._docker_available = available
        mgr.image_name = "tokenade"
        mgr.network = "tokenade-net"
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        status = mgr.get_status()
        assert status["docker_available"] is False
        assert status["containers_running"] == 0
        assert status["network_exists"] is False

    @patch.object(DockerSessionManager, "list_containers")
    @patch("subprocess.run")
    def test_full_status(self, mock_run, mock_list):
        mock_list.return_value = [
            DockerContainer("id1", "tokenade-0", "img", "Up", "", ""),
            DockerContainer("id2", "other", "img", "Up", "", ""),
        ]
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mgr = self._mgr(available=True)
        status = mgr.get_status()
        assert status["docker_available"] is True
        assert status["containers_running"] == 1  # only tokenade-0
        assert status["network_exists"] is True

    @patch.object(DockerSessionManager, "list_containers", return_value=[])
    @patch("subprocess.run")
    def test_network_not_exists(self, mock_run, _mock):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        mgr = self._mgr(available=True)
        status = mgr.get_status()
        assert status["network_exists"] is False

    @patch.object(DockerSessionManager, "list_containers", return_value=[])
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 5))
    def test_network_timeout(self, _mock_run, _mock_list):
        mgr = self._mgr(available=True)
        status = mgr.get_status()
        assert status["network_exists"] is False
