"""
Unit tests for Docker and Kubernetes integration modules.

All subprocess calls are mocked. No actual docker/kubectl calls are made.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.core.integration.docker_manager import DockerSessionManager, DockerContainer  # noqa: E402

try:
    import yaml  # noqa: F401
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig  # noqa: E402


# ---------------------------------------------------------------------------
# DockerSessionManager Tests
# ---------------------------------------------------------------------------


class TestDockerSessionManagerAvailability(unittest.TestCase):
    """Test Docker availability checks."""

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_is_available_when_docker_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        mgr = DockerSessionManager()
        self.assertFalse(mgr.is_available())

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_is_available_when_docker_present(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Docker version 24.0.0")
        mgr = DockerSessionManager()
        self.assertTrue(mgr.is_available())

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_is_available_timeout(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="docker", timeout=5)
        mgr = DockerSessionManager()
        self.assertFalse(mgr.is_available())


class TestDockerSessionManagerCreateContainer(unittest.TestCase):
    """Test create_session_container command construction."""

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_create_session_container_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123def456\n")
        mgr = DockerSessionManager(image_name="tokenade:latest")

        with patch("os.path.isfile", return_value=True), \
                patch("os.path.abspath", return_value="/tmp/session.tokenade"):
            container_id = mgr.create_session_container(
                session_file="/tmp/session.tokenade",
                name="test-container",
                port=9222,
            )

        self.assertEqual(container_id, "abc123def456")
        call_args = mock_run.call_args[0][0]
        self.assertIn("docker", call_args)
        self.assertIn("run", call_args)
        self.assertIn("-d", call_args)
        self.assertIn("--name", call_args)
        self.assertIn("test-container", call_args)
        self.assertIn("-p", call_args)
        self.assertIn("9222:9222", call_args)

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_create_session_container_file_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Docker version 24.0.0")
        mgr = DockerSessionManager()
        call_count_after_init = mock_run.call_count
        with patch("os.path.isfile", return_value=False):
            result = mgr.create_session_container(
                session_file="/nonexistent/file.tokenade",
                name="test",
            )
        self.assertIsNone(result)
        self.assertEqual(mock_run.call_count, call_count_after_init)

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_create_session_container_docker_not_available(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        mgr = DockerSessionManager()
        result = mgr.create_session_container(
            session_file="/tmp/s.tokenade",
            name="test",
        )
        self.assertIsNone(result)

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_create_session_container_failure(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.CalledProcessError(1, "docker", stderr="error")
        mgr = DockerSessionManager()
        with patch("os.path.isfile", return_value=True), \
                patch("os.path.abspath", return_value="/tmp/s.tokenade"):
            result = mgr.create_session_container(
                session_file="/tmp/s.tokenade",
                name="fail",
            )
        self.assertIsNone(result)


class TestDockerSessionManagerListContainers(unittest.TestCase):
    """Test list_containers parsing."""

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_list_containers_parses_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc123\tmy-container\ttokenade:latest\tUp 5 minutes\t0.0.0.0:9222->9222/tcp\t2024-01-01 12:00:00\n",
        )
        mgr = DockerSessionManager()
        containers = mgr.list_containers()
        self.assertEqual(len(containers), 1)
        self.assertEqual(containers[0].id, "abc123")
        self.assertEqual(containers[0].name, "my-container")
        self.assertEqual(containers[0].image, "tokenade:latest")
        self.assertIn("Up", containers[0].status)

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_list_containers_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mgr = DockerSessionManager()
        containers = mgr.list_containers()
        self.assertEqual(containers, [])

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_list_containers_docker_not_available(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        mgr = DockerSessionManager()
        containers = mgr.list_containers()
        self.assertEqual(containers, [])

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_list_containers_all_flag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mgr = DockerSessionManager()
        mgr.list_containers(all_containers=True)
        call_args = mock_run.call_args[0][0]
        self.assertIn("-a", call_args)


class TestDockerSessionManagerStopRemove(unittest.TestCase):
    """Test stop and remove container."""

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_stop_container_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mgr = DockerSessionManager()
        self.assertTrue(mgr.stop_container("abc123"))
        call_args = mock_run.call_args[0][0]
        self.assertIn("stop", call_args)
        self.assertIn("abc123", call_args)

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_stop_container_failure(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.CalledProcessError(1, "docker")
        mgr = DockerSessionManager()
        self.assertFalse(mgr.stop_container("abc123"))

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_remove_container_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mgr = DockerSessionManager()
        self.assertTrue(mgr.remove_container("abc123"))
        call_args = mock_run.call_args[0][0]
        self.assertIn("rm", call_args)
        self.assertIn("abc123", call_args)

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_remove_container_force(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        mgr = DockerSessionManager()
        mgr.remove_container("abc123", force=True)
        call_args = mock_run.call_args[0][0]
        self.assertIn("-f", call_args)


class TestDockerSessionManagerBuildImage(unittest.TestCase):
    """Test build_image command."""

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_build_image_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Successfully built abc")
        mgr = DockerSessionManager(image_name="tokenade")
        self.assertTrue(mgr.build_image(tag="tokenade:v1"))
        call_args = mock_run.call_args[0][0]
        self.assertIn("build", call_args)
        self.assertIn("-t", call_args)
        self.assertIn("tokenade:v1", call_args)

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_build_image_default_tag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        mgr = DockerSessionManager(image_name="tokenade")
        mgr.build_image()
        call_args = mock_run.call_args[0][0]
        self.assertIn("tokenade", call_args)


class TestDockerSessionManagerPullImage(unittest.TestCase):
    """Test pull_image command."""

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_pull_image_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Status: Downloaded")
        mgr = DockerSessionManager(image_name="tokenade")
        self.assertTrue(mgr.pull_image(tag="latest"))
        call_args = mock_run.call_args[0][0]
        self.assertIn("pull", call_args)
        self.assertIn("tokenade:latest", call_args)


class TestDockerSessionManagerRunBatch(unittest.TestCase):
    """Test run_batch."""

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_run_batch(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
        mgr = DockerSessionManager()

        with patch("os.path.isfile", return_value=True), \
                patch("os.path.abspath", side_effect=lambda x: x):
            results = mgr.run_batch(
                session_files=["/tmp/s1.tokenade", "/tmp/s2.tokenade"],
                prefix="batch",
            )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["name"], "batch-0")
        self.assertEqual(results[0]["port"], 9222)
        self.assertEqual(results[0]["status"], "running")
        self.assertEqual(results[1]["name"], "batch-1")
        self.assertEqual(results[1]["port"], 9223)


class TestDockerSessionManagerCleanup(unittest.TestCase):
    """Test cleanup."""

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_cleanup_stops_and_removes(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc1\ttokenade-1\ttokenade:latest\tUp 5 min\t0.0.0.0:9222->9222/tcp\t2024-01-01\nxyz2\tother-1\tnginx\tUp 10 min\t80/tcp\t2024-01-01\n",
        )
        mgr = DockerSessionManager()
        count = mgr.cleanup(remove_all=True)
        self.assertEqual(count, 1)
        self.assertTrue(mock_run.called)


class TestDockerSessionManagerGetStatus(unittest.TestCase):
    """Test get_status."""

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_get_status_docker_unavailable(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        mgr = DockerSessionManager()
        status = mgr.get_status()
        self.assertFalse(status["docker_available"])
        self.assertEqual(status["containers_running"], 0)
        self.assertFalse(status["network_exists"])

    @patch("tokenade.core.integration.docker_manager.subprocess.run")
    def test_get_status_docker_available(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "--version" in cmd:
                return MagicMock(returncode=0, stdout="Docker 24.0")
            if "ps" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="abc\ttokenade-1\ttokenade:latest\tUp\t0.0.0.0:9222->9222/tcp\t2024-01-01\n",
                )
            if "network" in cmd:
                return MagicMock(returncode=0, stdout="[]")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        mgr = DockerSessionManager()
        status = mgr.get_status()
        self.assertTrue(status["docker_available"])
        self.assertEqual(status["containers_running"], 1)
        self.assertTrue(status["network_exists"])


class TestDockerContainerDataclass(unittest.TestCase):
    """Test DockerContainer dataclass."""

    def test_creation(self):
        c = DockerContainer(
            id="abc123",
            name="test",
            image="tokenade:latest",
            status="Up 5 minutes",
            ports="0.0.0.0:9222->9222/tcp",
            created="2024-01-01",
        )
        self.assertEqual(c.id, "abc123")
        self.assertEqual(c.name, "test")
        self.assertEqual(c.image, "tokenade:latest")
        self.assertEqual(c.status, "Up 5 minutes")
        self.assertEqual(c.ports, "0.0.0.0:9222->9222/tcp")
        self.assertEqual(c.created, "2024-01-01")


# ---------------------------------------------------------------------------
# KubernetesManager Tests
# ---------------------------------------------------------------------------


class TestKubernetesManagerAvailability(unittest.TestCase):
    """Test kubectl availability checks."""

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_is_available_when_kubectl_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        mgr = KubernetesManager()
        self.assertFalse(mgr.is_available())

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_is_available_when_kubectl_present(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Client Version: v1.28.0")
        mgr = KubernetesManager()
        self.assertTrue(mgr.is_available())


@unittest.skipUnless(HAS_YAML, "PyYAML not installed")
class TestKubernetesManagerDeploymentYaml(unittest.TestCase):
    """Test generate_deployment_yaml output."""

    def test_generate_deployment_yaml_valid(self):
        import yaml
        mgr = KubernetesManager()
        output = mgr.generate_deployment_yaml()
        data = yaml.safe_load(output)
        self.assertEqual(data["apiVersion"], "apps/v1")
        self.assertEqual(data["kind"], "Deployment")
        self.assertEqual(data["metadata"]["name"], "tokenade")
        self.assertEqual(data["spec"]["replicas"], 1)
        containers = data["spec"]["template"]["spec"]["containers"]
        self.assertEqual(len(containers), 1)
        self.assertEqual(containers[0]["name"], "tokenade")

    def test_generate_deployment_yaml_with_configmap(self):
        import yaml
        mgr = KubernetesManager()
        output = mgr.generate_deployment_yaml(session_configmap="my-sessions")
        data = yaml.safe_load(output)
        volumes = data["spec"]["template"]["spec"]["volumes"]
        self.assertEqual(volumes[0]["configMap"]["name"], "my-sessions")

    def test_generate_deployment_yaml_custom_config(self):
        import yaml
        config = KubernetesConfig(
            namespace="production",
            replicas=3,
            port=8080,
            image="tokenade:prod",
        )
        mgr = KubernetesManager(config=config)
        output = mgr.generate_deployment_yaml()
        data = yaml.safe_load(output)
        self.assertEqual(data["metadata"]["namespace"], "production")
        self.assertEqual(data["spec"]["replicas"], 3)
        container = data["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["image"], "tokenade:prod")
        self.assertIn("8080", container["args"])


@unittest.skipUnless(HAS_YAML, "PyYAML not installed")
class TestKubernetesManagerSidecarYaml(unittest.TestCase):
    """Test generate_sidecar_yaml output."""

    def test_generate_sidecar_yaml_valid(self):
        import yaml
        mgr = KubernetesManager()
        output = mgr.generate_sidecar_yaml(
            main_container_image="myapp:latest",
            session_configmap="sessions-cm",
        )
        data = yaml.safe_load(output)
        containers = data["spec"]["template"]["spec"]["containers"]
        self.assertEqual(len(containers), 2)
        names = [c["name"] for c in containers]
        self.assertIn("main-app", names)
        self.assertIn("tokenade-sidecar", names)

        sidecar = [c for c in containers if c["name"] == "tokenade-sidecar"][0]
        self.assertIn("proxy", sidecar["args"])

    def test_generate_sidecar_yaml_shares_volume(self):
        import yaml
        mgr = KubernetesManager()
        output = mgr.generate_sidecar_yaml(
            main_container_image="app:v1",
            session_configmap="cm-sessions",
        )
        data = yaml.safe_load(output)
        volumes = data["spec"]["template"]["spec"]["volumes"]
        self.assertEqual(volumes[0]["configMap"]["name"], "cm-sessions")


@unittest.skipUnless(HAS_YAML, "PyYAML not installed")
class TestKubernetesManagerServiceYaml(unittest.TestCase):
    """Test generate_service_yaml output."""

    def test_generate_service_yaml_valid(self):
        import yaml
        mgr = KubernetesManager()
        output = mgr.generate_service_yaml()
        data = yaml.safe_load(output)
        self.assertEqual(data["apiVersion"], "v1")
        self.assertEqual(data["kind"], "Service")
        self.assertEqual(data["metadata"]["name"], "tokenade")
        self.assertEqual(data["spec"]["type"], "ClusterIP")
        ports = data["spec"]["ports"]
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0]["port"], 9222)


@unittest.skipUnless(HAS_YAML, "PyYAML not installed")
class TestKubernetesManagerConfigMapYaml(unittest.TestCase):
    """Test generate_configmap_yaml output."""

    def test_generate_configmap_yaml_valid(self):
        import yaml
        mgr = KubernetesManager()
        output = mgr.generate_configmap_yaml({
            "session1.tokenade": "data1",
            "session2.tokenade": "data2",
        })
        data = yaml.safe_load(output)
        self.assertEqual(data["apiVersion"], "v1")
        self.assertEqual(data["kind"], "ConfigMap")
        self.assertEqual(data["metadata"]["name"], "tokenade-sessions")
        self.assertIn("session1.tokenade", data["data"])
        self.assertIn("session2.tokenade", data["data"])

    def test_generate_configmap_yaml_empty(self):
        import yaml
        mgr = KubernetesManager()
        output = mgr.generate_configmap_yaml({})
        data = yaml.safe_load(output)
        self.assertEqual(data["data"], {})


class TestKubernetesManagerApplyManifests(unittest.TestCase):
    """Test apply_manifests command."""

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_apply_manifests_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='deployment.apps/tokenade created\nservice/tokenade created\n',
        )
        mgr = KubernetesManager()
        result = mgr.apply_manifests("apiVersion: v1\nkind: Service\n")
        self.assertTrue(result)
        call_args = mock_run.call_args[0][0]
        self.assertIn("kubectl", call_args)
        self.assertIn("apply", call_args)
        self.assertIn("-f", call_args)

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_apply_manifests_failure(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.CalledProcessError(1, "kubectl", stderr="error")
        mgr = KubernetesManager()
        result = mgr.apply_manifests("invalid yaml")
        self.assertFalse(result)

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_apply_manifests_kubectl_unavailable(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        mgr = KubernetesManager()
        result = mgr.apply_manifests("yaml content")
        self.assertFalse(result)


class TestKubernetesManagerScale(unittest.TestCase):
    """Test scale_deployment command."""

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_scale_deployment_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="scaled")
        mgr = KubernetesManager()
        self.assertTrue(mgr.scale_deployment(replicas=5))
        call_args = mock_run.call_args[0][0]
        self.assertIn("scale", call_args)
        self.assertIn("--replicas=5", call_args)

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_scale_deployment_failure(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.CalledProcessError(1, "kubectl")
        mgr = KubernetesManager()
        self.assertFalse(mgr.scale_deployment(replicas=3))


class TestKubernetesManagerGetPods(unittest.TestCase):
    """Test get_pods command."""

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_get_pods_parses_output(self, mock_run):
        pods_response = {
            "items": [
                {
                    "metadata": {"name": "tokenade-abc123", "namespace": "default"},
                    "status": {
                        "phase": "Running",
                        "podIP": "10.0.0.1",
                        "containerStatuses": [{"restartCount": 0}],
                    },
                    "spec": {"nodeName": "node1"},
                }
            ]
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(pods_response),
        )
        mgr = KubernetesManager()
        pods = mgr.get_pods()
        self.assertEqual(len(pods), 1)
        self.assertEqual(pods[0]["name"], "tokenade-abc123")
        self.assertEqual(pods[0]["status"], "Running")
        self.assertEqual(pods[0]["pod_ip"], "10.0.0.1")
        self.assertEqual(pods[0]["restart_count"], 0)

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_get_pods_empty(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"items": []}),
        )
        mgr = KubernetesManager()
        pods = mgr.get_pods()
        self.assertEqual(pods, [])

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_get_pods_kubectl_unavailable(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        mgr = KubernetesManager()
        pods = mgr.get_pods()
        self.assertEqual(pods, [])


class TestKubernetesManagerGetLogs(unittest.TestCase):
    """Test get_logs command."""

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_get_logs_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="log line 1\nlog line 2\n",
        )
        mgr = KubernetesManager()
        logs = mgr.get_logs("tokenade-abc123")
        self.assertEqual(logs, "log line 1\nlog line 2\n")
        call_args = mock_run.call_args[0][0]
        self.assertIn("logs", call_args)
        self.assertIn("tokenade-abc123", call_args)

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_get_logs_failure(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.CalledProcessError(1, "kubectl")
        mgr = KubernetesManager()
        logs = mgr.get_logs("bad-pod")
        self.assertEqual(logs, "")


class TestKubernetesManagerDeleteDeployment(unittest.TestCase):
    """Test delete_deployment command."""

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_delete_deployment_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="deleted")
        mgr = KubernetesManager()
        init_calls = mock_run.call_count
        self.assertTrue(mgr.delete_deployment("tokenade"))
        self.assertEqual(mock_run.call_count, init_calls + 2)

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_delete_deployment_partial_failure(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "version" in cmd:
                return MagicMock(returncode=0, stdout="Client Version: v1.28.0")
            if "deployment" in cmd:
                return MagicMock(returncode=0, stdout="deleted")
            import subprocess as sp
            raise sp.CalledProcessError(1, "kubectl")
        mock_run.side_effect = side_effect

        mgr = KubernetesManager()
        result = mgr.delete_deployment("tokenade")
        self.assertFalse(result)


class TestKubernetesConfigDataclass(unittest.TestCase):
    """Test KubernetesConfig defaults."""

    def test_defaults(self):
        cfg = KubernetesConfig()
        self.assertEqual(cfg.namespace, "default")
        self.assertEqual(cfg.replicas, 1)
        self.assertEqual(cfg.port, 9222)
        self.assertIn("cpu", cfg.resource_requests)
        self.assertIn("memory", cfg.resource_limits)

    def test_custom_values(self):
        cfg = KubernetesConfig(
            namespace="staging",
            replicas=5,
            port=8080,
        )
        self.assertEqual(cfg.namespace, "staging")
        self.assertEqual(cfg.replicas, 5)
        self.assertEqual(cfg.port, 8080)


class TestKubernetesManagerGetDeploymentStatus(unittest.TestCase):
    """Test get_deployment_status."""

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_get_deployment_status_success(self, mock_run):
        deployment_response = {
            "status": {
                "replicas": 3,
                "readyReplicas": 3,
                "availableReplicas": 3,
                "conditions": [
                    {"type": "Available", "status": "True", "message": "Deployment has minimum availability."},
                ],
            }
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(deployment_response),
        )
        mgr = KubernetesManager()
        status = mgr.get_deployment_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["replicas"], 3)
        self.assertEqual(status["ready_replicas"], 3)

    @patch("tokenade.core.integration.kubernetes.subprocess.run")
    def test_get_deployment_status_kubectl_unavailable(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        mgr = KubernetesManager()
        status = mgr.get_deployment_status()
        self.assertFalse(status["available"])


if __name__ == "__main__":
    unittest.main()
