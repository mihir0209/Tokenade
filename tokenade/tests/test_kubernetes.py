"""Tests for tokenade.core.integration.kubernetes"""
import json
import subprocess
from unittest.mock import patch, MagicMock


from tokenade.core.integration.kubernetes import KubernetesConfig, KubernetesManager


# ---------------------------------------------------------------------------
# KubernetesConfig
# ---------------------------------------------------------------------------

class TestKubernetesConfig:
    def test_defaults(self):
        cfg = KubernetesConfig()
        assert cfg.namespace == "default"
        assert cfg.image == "tokenade:latest"
        assert cfg.replicas == 1
        assert cfg.port == 9222
        assert cfg.session_mount_path == "/app/sessions"
        assert cfg.service_account == "tokenade"
        assert cfg.resource_requests == {"cpu": "100m", "memory": "128Mi"}
        assert cfg.resource_limits == {"cpu": "500m", "memory": "512Mi"}
        assert cfg.env_vars == {}

    def test_custom_values(self):
        cfg = KubernetesConfig(
            namespace="prod",
            image="myimg:v2",
            replicas=3,
            port=8080,
            env_vars={"FOO": "bar"},
        )
        assert cfg.namespace == "prod"
        assert cfg.image == "myimg:v2"
        assert cfg.replicas == 3
        assert cfg.port == 8080
        assert cfg.env_vars == {"FOO": "bar"}


# ---------------------------------------------------------------------------
# KubernetesManager – availability checks
# ---------------------------------------------------------------------------

class TestKubectlAvailability:
    @patch("subprocess.run")
    def test_available(self, mock_run):
        mock_run.return_value = MagicMock()
        mgr = KubernetesManager()
        assert mgr.is_available() is True
        mock_run.assert_called_once()

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_unavailable_file_not_found(self, _mock):
        mgr = KubernetesManager()
        assert mgr.is_available() is False

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "kubectl"))
    def test_unavailable_called_process_error(self, _mock):
        mgr = KubernetesManager()
        assert mgr.is_available() is False

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("kubectl", 5))
    def test_unavailable_timeout(self, _mock):
        mgr = KubernetesManager()
        assert mgr.is_available() is False


# ---------------------------------------------------------------------------
# generate_deployment_yaml
# ---------------------------------------------------------------------------

class TestGenerateDeploymentYAML:
    def _mgr(self, **overrides):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig(**overrides)
        return mgr

    def test_basic_deployment(self):
        mgr = self._mgr()
        yaml = mgr.generate_deployment_yaml()
        assert "apiVersion: apps/v1" in yaml
        assert "kind: Deployment" in yaml
        assert "name: tokenade" in yaml
        assert "namespace: default" in yaml
        assert "replicas: 1" in yaml
        assert "serviceAccountName: tokenade" in yaml
        assert "image: tokenade:latest" in yaml
        assert "containerPort: 9222" in yaml

    def test_custom_namespace_and_replicas(self):
        mgr = self._mgr(namespace="staging", replicas=5)
        yaml = mgr.generate_deployment_yaml()
        assert "namespace: staging" in yaml
        assert "replicas: 5" in yaml

    def test_custom_configmap_name(self):
        mgr = self._mgr()
        yaml = mgr.generate_deployment_yaml(session_configmap="my-cm")
        assert "name: my-cm" in yaml

    def test_default_configmap_name(self):
        mgr = self._mgr()
        yaml = mgr.generate_deployment_yaml()
        assert "name: tokenade-sessions" in yaml

    def test_env_vars_built_but_not_in_output(self):
        mgr = self._mgr(env_vars={"TOKEN": "abc", "DEBUG": "1"})
        yaml = mgr.generate_deployment_yaml()
        assert "- name: TOKEN" not in yaml

    def test_resource_requests_and_limits(self):
        mgr = self._mgr(
            resource_requests={"cpu": "200m", "memory": "256Mi"},
            resource_limits={"cpu": "1", "memory": "1Gi"},
        )
        yaml = mgr.generate_deployment_yaml()
        assert "cpu: 200m" in yaml
        assert "memory: 256Mi" in yaml
        assert "cpu: 1" in yaml
        assert "memory: 1Gi" in yaml

    def test_probes_present(self):
        mgr = self._mgr()
        yaml = mgr.generate_deployment_yaml()
        assert "livenessProbe:" in yaml
        assert "readinessProbe:" in yaml
        assert "tcpSocket:" in yaml

    def test_volume_mounts(self):
        mgr = self._mgr(session_mount_path="/data/sessions")
        yaml = mgr.generate_deployment_yaml()
        assert "mountPath: /data/sessions" in yaml


# ---------------------------------------------------------------------------
# generate_service_yaml
# ---------------------------------------------------------------------------

class TestGenerateServiceYAML:
    def _mgr(self, **overrides):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig(**overrides)
        return mgr

    def test_basic_service(self):
        mgr = self._mgr()
        yaml = mgr.generate_service_yaml()
        assert "apiVersion: v1" in yaml
        assert "kind: Service" in yaml
        assert "name: tokenade" in yaml
        assert "namespace: default" in yaml
        assert "port: 9222" in yaml
        assert "targetPort: 9222" in yaml
        assert "type: ClusterIP" in yaml

    def test_custom_port(self):
        mgr = self._mgr(port=8080)
        yaml = mgr.generate_service_yaml()
        assert "port: 8080" in yaml
        assert "targetPort: 8080" in yaml

    def test_custom_namespace(self):
        mgr = self._mgr(namespace="kube-system")
        yaml = mgr.generate_service_yaml()
        assert "namespace: kube-system" in yaml


# ---------------------------------------------------------------------------
# generate_configmap_yaml
# ---------------------------------------------------------------------------

class TestGenerateConfigMapYAML:
    def _mgr(self, **overrides):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig(**overrides)
        return mgr

    def test_empty_data(self):
        mgr = self._mgr()
        yaml = mgr.generate_configmap_yaml({})
        assert "apiVersion: v1" in yaml
        assert "kind: ConfigMap" in yaml
        assert "name: tokenade-sessions" in yaml
        assert "data: {}" in yaml

    def test_with_session_files(self):
        mgr = self._mgr()
        yaml = mgr.generate_configmap_yaml({"file1.json": '{"k":"v"}'})
        assert "data:" in yaml
        escaped_v = '{"k":"v"}'.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        assert f'file1.json: "{escaped_v}"' in yaml

    def test_escape_special_chars(self):
        mgr = self._mgr()
        content = 'line1\nline2\\back\\"quote'
        yaml = mgr.generate_configmap_yaml({"f.txt": content})
        escaped = content.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        assert f'f.txt: "{escaped}"' in yaml

    def test_custom_namespace(self):
        mgr = self._mgr(namespace="ns2")
        yaml = mgr.generate_configmap_yaml({"a.txt": "a"})
        assert "namespace: ns2" in yaml


# ---------------------------------------------------------------------------
# generate_sidecar_yaml
# ---------------------------------------------------------------------------

class TestGenerateSidecarYAML:
    def _mgr(self, **overrides):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig(**overrides)
        return mgr

    def test_basic_sidecar(self):
        mgr = self._mgr()
        yaml = mgr.generate_sidecar_yaml("myapp:latest", "my-cm")
        assert "kind: Deployment" in yaml
        assert "name: tokenade-sidecar" in yaml
        assert "name: main-app" in yaml
        assert "image: myapp:latest" in yaml
        assert "name: tokenade-sidecar" in yaml
        assert "image: tokenade:latest" in yaml
        assert "name: shared-sessions" in yaml
        assert "name: my-cm" in yaml

    def test_custom_config_in_sidecar(self):
        mgr = self._mgr(namespace="prod", replicas=3, port=3000)
        yaml = mgr.generate_sidecar_yaml("app:v1", "cm-prod")
        assert "namespace: prod" in yaml
        assert "replicas: 3" in yaml
        assert "containerPort: 3000" in yaml
        assert "cm-prod" in yaml


# ---------------------------------------------------------------------------
# apply_manifests
# ---------------------------------------------------------------------------

class TestApplyManifests:
    def _mgr(self, available=True):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig()
        mgr._kubectl_available = available
        return mgr

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="deployment.apps/tokenade created\n", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.apply_manifests("yaml content") is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "kubectl" in call_args[0][0]
        assert "apply" in call_args[0][0]

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.apply_manifests("yaml content") is False

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "kubectl", stderr="err"))
    def test_called_process_error(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.apply_manifests("yaml") is False

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("kubectl", 30))
    def test_timeout(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.apply_manifests("yaml") is False


# ---------------------------------------------------------------------------
# get_deployment_status
# ---------------------------------------------------------------------------

class TestGetDeploymentStatus:
    def _mgr(self, available=True):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig()
        mgr._kubectl_available = available
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        result = mgr.get_deployment_status()
        assert result["available"] is False
        assert "kubectl not available" in result["error"]

    @patch("subprocess.run")
    def test_success(self, mock_run):
        data = {
            "status": {
                "replicas": 3,
                "readyReplicas": 2,
                "availableReplicas": 2,
                "conditions": [{"type": "Available", "status": "True", "message": "ok"}],
            }
        }
        mock_run.return_value = MagicMock(stdout=json.dumps(data), stderr="")
        mgr = self._mgr(available=True)
        result = mgr.get_deployment_status("my-deploy")
        assert result["available"] is True
        assert result["name"] == "my-deploy"
        assert result["replicas"] == 3
        assert result["ready_replicas"] == 2
        assert result["available_replicas"] == 2
        assert len(result["conditions"]) == 1
        assert result["conditions"][0]["type"] == "Available"

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "kubectl"))
    def test_process_error(self, _mock):
        mgr = self._mgr(available=True)
        result = mgr.get_deployment_status()
        assert result["available"] is False
        assert "error" in result

    @patch("subprocess.run")
    def test_json_decode_error(self, mock_run):
        mock_run.return_value = MagicMock(stdout="not json", stderr="")
        mgr = self._mgr(available=True)
        result = mgr.get_deployment_status()
        assert result["available"] is False


# ---------------------------------------------------------------------------
# scale_deployment
# ---------------------------------------------------------------------------

class TestScaleDeployment:
    def _mgr(self, available=True):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig()
        mgr._kubectl_available = available
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.scale_deployment(5) is False

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="scaled", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.scale_deployment(5) is True
        cmd = mock_run.call_args[0][0]
        assert "--replicas=5" in cmd

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "kubectl"))
    def test_failure(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.scale_deployment(5) is False

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("kubectl", 10))
    def test_timeout(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.scale_deployment(5) is False


# ---------------------------------------------------------------------------
# delete_deployment
# ---------------------------------------------------------------------------

class TestDeleteDeployment:
    def _mgr(self, available=True):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig()
        mgr._kubectl_available = available
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.delete_deployment() is False

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="deleted", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.delete_deployment("my-deploy") is True
        assert mock_run.call_count == 2  # deployment + service

    @patch("subprocess.run")
    def test_partial_failure(self, mock_run):
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(stdout="deleted", stderr="")
            raise subprocess.CalledProcessError(1, "kubectl")
        mock_run.side_effect = side_effect
        mgr = self._mgr(available=True)
        assert mgr.delete_deployment("my-deploy") is False


# ---------------------------------------------------------------------------
# get_pods
# ---------------------------------------------------------------------------

class TestGetPods:
    def _mgr(self, available=True):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig()
        mgr._kubectl_available = available
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.get_pods() == []

    @patch("subprocess.run")
    def test_success(self, mock_run):
        data = {
            "items": [
                {
                    "metadata": {"name": "pod-1", "namespace": "default"},
                    "status": {"phase": "Running", "podIP": "10.0.0.1", "containerStatuses": [{"restartCount": 2}]},
                    "spec": {"nodeName": "node-1"},
                },
                {
                    "metadata": {"name": "pod-2", "namespace": "default"},
                    "status": {"phase": "Pending", "podIP": "", "containerStatuses": []},
                    "spec": {"nodeName": "node-2"},
                },
            ]
        }
        mock_run.return_value = MagicMock(stdout=json.dumps(data), stderr="")
        mgr = self._mgr(available=True)
        pods = mgr.get_pods("my-app")
        assert len(pods) == 2
        assert pods[0]["name"] == "pod-1"
        assert pods[0]["status"] == "Running"
        assert pods[0]["pod_ip"] == "10.0.0.1"
        assert pods[0]["restart_count"] == 2
        assert pods[1]["restart_count"] == 0

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "kubectl"))
    def test_process_error(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.get_pods() == []

    @patch("subprocess.run")
    def test_json_error(self, mock_run):
        mock_run.return_value = MagicMock(stdout="bad", stderr="")
        mgr = self._mgr(available=True)
        assert mgr.get_pods() == []


# ---------------------------------------------------------------------------
# get_logs
# ---------------------------------------------------------------------------

class TestGetLogs:
    def _mgr(self, available=True):
        mgr = object.__new__(KubernetesManager)
        mgr.config = KubernetesConfig()
        mgr._kubectl_available = available
        return mgr

    def test_not_available(self):
        mgr = self._mgr(available=False)
        assert mgr.get_logs("pod-1") == ""

    @patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="log line 1\nlog line 2\n", stderr="")
        mgr = self._mgr(available=True)
        logs = mgr.get_logs("pod-1", tail=50)
        assert "log line 1" in logs
        cmd = mock_run.call_args[0][0]
        assert "--tail" in cmd
        assert "50" in cmd

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "kubectl"))
    def test_error(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.get_logs("pod-1") == ""

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("kubectl", 10))
    def test_timeout(self, _mock):
        mgr = self._mgr(available=True)
        assert mgr.get_logs("pod-1") == ""
