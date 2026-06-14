"""
Kubernetes sidecar mode for Tokenade.
"""
import subprocess
import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class KubernetesConfig:
    """Kubernetes deployment configuration."""
    namespace: str = "default"
    image: str = "tokenade:latest"
    replicas: int = 1
    port: int = 9222
    session_mount_path: str = "/app/sessions"
    service_account: str = "tokenade"
    resource_requests: Dict[str, str] = field(default_factory=lambda: {"cpu": "100m", "memory": "128Mi"})
    resource_limits: Dict[str, str] = field(default_factory=lambda: {"cpu": "500m", "memory": "512Mi"})
    env_vars: Dict[str, str] = field(default_factory=dict)


class KubernetesManager:
    """Manage Tokenade deployments in Kubernetes."""

    def __init__(self, config: Optional[KubernetesConfig] = None):
        self.config = config or KubernetesConfig()
        self._kubectl_available = self._check_kubectl()

    def _check_kubectl(self) -> bool:
        """Check if kubectl is available."""
        try:
            subprocess.run(
                ["kubectl", "version", "--client"],
                capture_output=True,
                check=True,
                timeout=5,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def is_available(self) -> bool:
        """Check if kubectl is available."""
        return self._kubectl_available

    def generate_deployment_yaml(self, session_configmap: Optional[str] = None) -> str:
        """Generate Kubernetes Deployment YAML manifest as a string."""
        cfg = self.config
        cm_name = session_configmap or "tokenade-sessions"

        env_lines = ""
        for key, val in cfg.env_vars.items():
            env_lines += f"            - name: {key}\n              value: \"{val}\"\n"

        lines = [
            "apiVersion: apps/v1",
            "kind: Deployment",
            "metadata:",
            "  name: tokenade",
            f"  namespace: {cfg.namespace}",
            "  labels:",
            "    app: tokenade",
            "spec:",
            f"  replicas: {cfg.replicas}",
            "  selector:",
            "    matchLabels:",
            "      app: tokenade",
            "  template:",
            "    metadata:",
            "      labels:",
            "        app: tokenade",
            "    spec:",
            f"      serviceAccountName: {cfg.service_account}",
            "      containers:",
            "        - name: tokenade",
            f"          image: {cfg.image}",
            f'          args: ["proxy", "--host", "0.0.0.0", "--port", "{cfg.port}"]',
            "          ports:",
            f"            - containerPort: {cfg.port}",
            "              protocol: TCP",
            "          resources:",
            "            requests:",
            f"              cpu: {cfg.resource_requests.get('cpu', '100m')}",
            f"              memory: {cfg.resource_requests.get('memory', '128Mi')}",
            "            limits:",
            f"              cpu: {cfg.resource_limits.get('cpu', '500m')}",
            f"              memory: {cfg.resource_limits.get('memory', '512Mi')}",
            "          livenessProbe:",
            "            tcpSocket:",
            f"              port: {cfg.port}",
            "            initialDelaySeconds: 5",
            "            periodSeconds: 10",
            "          readinessProbe:",
            "            tcpSocket:",
            f"              port: {cfg.port}",
            "            initialDelaySeconds: 3",
            "            periodSeconds: 5",
            "          volumeMounts:",
            "            - name: sessions",
            f"              mountPath: {cfg.session_mount_path}",
            "              readOnly: true",
            "      volumes:",
            "        - name: sessions",
            "          configMap:",
            f"            name: {cm_name}",
        ]
        return "\n".join(lines) + "\n"

    def generate_sidecar_yaml(self, main_container_image: str, session_configmap: str) -> str:
        """Generate YAML for Tokenade as a sidecar container alongside a main app container."""
        cfg = self.config

        yaml_content = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: tokenade-sidecar
  namespace: {cfg.namespace}
  labels:
    app: tokenade-sidecar
spec:
  replicas: {cfg.replicas}
  selector:
    matchLabels:
      app: tokenade-sidecar
  template:
    metadata:
      labels:
        app: tokenade-sidecar
    spec:
      serviceAccountName: {cfg.service_account}
      containers:
        - name: main-app
          image: {main_container_image}
          volumeMounts:
            - name: shared-sessions
              mountPath: {cfg.session_mount_path}
        - name: tokenade-sidecar
          image: {cfg.image}
          args: ["proxy", "--host", "0.0.0.0", "--port", "{cfg.port}"]
          ports:
            - containerPort: {cfg.port}
              protocol: TCP
          resources:
            requests:
              cpu: {cfg.resource_requests.get("cpu", "100m")}
              memory: {cfg.resource_requests.get("memory", "128Mi")}
            limits:
              cpu: {cfg.resource_limits.get("cpu", "500m")}
              memory: {cfg.resource_limits.get("memory", "512Mi")}
          livenessProbe:
            tcpSocket:
              port: {cfg.port}
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            tcpSocket:
              port: {cfg.port}
            initialDelaySeconds: 3
            periodSeconds: 5
          volumeMounts:
            - name: shared-sessions
              mountPath: {cfg.session_mount_path}
              readOnly: true
      volumes:
        - name: shared-sessions
          configMap:
            name: {session_configmap}
"""
        return yaml_content

    def generate_service_yaml(self) -> str:
        """Generate Kubernetes Service YAML."""
        cfg = self.config

        yaml_content = f"""apiVersion: v1
kind: Service
metadata:
  name: tokenade
  namespace: {cfg.namespace}
  labels:
    app: tokenade
spec:
  selector:
    app: tokenade
  ports:
    - name: proxy
      port: {cfg.port}
      targetPort: {cfg.port}
      protocol: TCP
  type: ClusterIP
"""
        return yaml_content

    def generate_configmap_yaml(self, session_files: Dict[str, str]) -> str:
        """Generate ConfigMap from session files. session_files: {filename: content}"""
        cfg = self.config

        lines = [
            "apiVersion: v1",
            "kind: ConfigMap",
            "metadata:",
            "  name: tokenade-sessions",
            f"  namespace: {cfg.namespace}",
            "  labels:",
            "    app: tokenade",
        ]
        if session_files:
            lines.append("data:")
            for filename, content in session_files.items():
                escaped = content.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                lines.append(f'  {filename}: "{escaped}"')
        else:
            lines.append("data: {}")

        return "\n".join(lines) + "\n"

    def apply_manifests(self, yaml_content: str) -> bool:
        """Apply YAML manifests using kubectl apply -f -"""
        if not self._kubectl_available:
            logger.error("kubectl is not available")
            return False

        try:
            result = subprocess.run(
                ["kubectl", "apply", "-n", self.config.namespace, "-f", "-"],
                input=yaml_content,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            logger.info("Applied manifests: %s", result.stdout.strip())
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Failed to apply manifests: %s", e.stderr)
            return False
        except subprocess.TimeoutExpired:
            logger.error("Timeout applying manifests")
            return False

    def get_deployment_status(self, name: str = "tokenade") -> Dict:
        """Get deployment status."""
        if not self._kubectl_available:
            return {"available": False, "error": "kubectl not available"}

        try:
            result = subprocess.run(
                [
                    "kubectl", "get", "deployment", name,
                    "-n", self.config.namespace,
                    "-o", "json",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            data = json.loads(result.stdout)
            status = data.get("status", {})
            return {
                "available": True,
                "name": name,
                "replicas": status.get("replicas", 0),
                "ready_replicas": status.get("readyReplicas", 0),
                "available_replicas": status.get("availableReplicas", 0),
                "conditions": [
                    {
                        "type": c.get("type"),
                        "status": c.get("status"),
                        "message": c.get("message", ""),
                    }
                    for c in status.get("conditions", [])
                ],
            }
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            logger.error("Failed to get deployment status: %s", e)
            return {"available": False, "error": str(e)}

    def scale_deployment(self, replicas: int, name: str = "tokenade") -> bool:
        """Scale deployment."""
        if not self._kubectl_available:
            return False

        try:
            subprocess.run(
                [
                    "kubectl", "scale", "deployment", name,
                    f"--replicas={replicas}",
                    "-n", self.config.namespace,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            logger.info("Scaled deployment %s to %d replicas", name, replicas)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Failed to scale deployment %s: %s", name, e)
            return False

    def delete_deployment(self, name: str = "tokenade") -> bool:
        """Delete deployment and associated service."""
        if not self._kubectl_available:
            return False

        deleted = True
        for resource_type in ["deployment", "service"]:
            try:
                subprocess.run(
                    [
                        "kubectl", "delete", resource_type, name,
                        "-n", self.config.namespace,
                        "--ignore-not-found",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=15,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.error("Failed to delete %s %s: %s", resource_type, name, e)
                deleted = False

        if deleted:
            logger.info("Deleted deployment and service %s", name)
        return deleted

    def get_pods(self, name: str = "tokenade") -> List[Dict]:
        """List pods for the deployment."""
        if not self._kubectl_available:
            return []

        try:
            result = subprocess.run(
                [
                    "kubectl", "get", "pods",
                    "-n", self.config.namespace,
                    "-l", f"app={name}",
                    "-o", "json",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            data = json.loads(result.stdout)
            pods = []
            for item in data.get("items", []):
                metadata = item.get("metadata", {})
                status = item.get("status", {})
                spec = item.get("spec", {})
                pods.append({
                    "name": metadata.get("name", ""),
                    "namespace": metadata.get("namespace", ""),
                    "status": status.get("phase", "Unknown"),
                    "pod_ip": status.get("podIP", ""),
                    "node_name": spec.get("nodeName", ""),
                    "restart_count": sum(
                        cs.get("restartCount", 0)
                        for cs in status.get("containerStatuses", [])
                    ),
                })
            return pods
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            logger.error("Failed to get pods: %s", e)
            return []

    def get_logs(self, pod_name: str, tail: int = 100) -> str:
        """Get logs from a pod."""
        if not self._kubectl_available:
            return ""

        try:
            result = subprocess.run(
                [
                    "kubectl", "logs", pod_name,
                    "-n", self.config.namespace,
                    "--tail", str(tail),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Failed to get logs for %s: %s", pod_name, e)
            return ""
