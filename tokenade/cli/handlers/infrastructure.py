"""
Infrastructure CLI commands — fleet, container, k8s.
"""

import logging

logger = logging.getLogger("tokenade")


def cmd_fleet(args):
    """Fleet management — unified view across containers/pods."""
    from tokenade.core.integration.fleet import FleetManager

    fleet_action = getattr(args, "fleet_action", "status")
    manager = FleetManager()

    if fleet_action == "status":
        report = manager.status()
        fmt = getattr(args, "format", "text")
        if fmt == "json":
            print(report.to_json())
        else:
            print(report.to_table())

    elif fleet_action == "health":
        report = manager.health()
        fmt = getattr(args, "format", "text")
        if fmt == "json":
            print(report.to_json())
        else:
            print(report.to_table())

    elif fleet_action == "refresh":
        print("🔄 Refreshing sessions in all running containers...")
        results = manager.refresh_all()
        if not results:
            print("No running containers found")
            return
        for r in results:
            icon = "✅" if r["success"] else "❌"
            print(f"  {icon} {r['container']}")
            if r.get("error"):
                print(f"      {r['error'][:200]}")

    elif fleet_action == "logs":
        container = getattr(args, "container", None)
        if not container:
            print("❌ Specify container: tokenade fleet logs <container>")
            return
        lines = getattr(args, "lines", 50)
        output = manager.logs(container, lines=lines)
        print(output)

    else:
        print("Usage: tokenade fleet {status|health|refresh|logs}")

def cmd_container(args):
    """Docker container management."""
    action = getattr(args, "container_action", None)

    if action == "start":
        _container_start(args)
    elif action == "stop":
        _container_stop(args)
    elif action == "restart":
        _container_restart(args)
    elif action == "status":
        _container_status(args)
    elif action == "logs":
        _container_logs(args)
    elif action == "refresh":
        _container_refresh(args)
    elif action == "scale":
        _container_scale(args)
    elif action == "cleanup":
        _container_cleanup(args)
    elif action == "health":
        _container_health(args)
    elif action == "generate":
        _container_generate(args)
    else:
        print("Usage: tokenade container {start|stop|restart|status|logs|refresh|scale|cleanup|health|generate}")


def _container_start(args):
    """Start proxy and optionally API containers."""
    from tokenade.core.integration.docker_manager import DockerSessionManager
    from tokenade.core.integration.container_orchestrator import generate_compose_override
    from pathlib import Path

    docker = DockerSessionManager()
    if not docker.is_available():
        print("❌ Docker is not available. Install Docker and try again.")
        return

    sessions_dir = Path(args.sessions_dir)
    session_files = list(sessions_dir.glob("*.tokenade"))

    if not session_files:
        print(f"❌ No .tokenade files found in {sessions_dir}")
        return

    print("\n" + "=" * 60)
    print("TOKENADE - Container Start")
    print("=" * 60)
    print(f"\n📂 Sessions: {len(session_files)}")
    print(f"🔌 Proxy port: {args.proxy_port}")

    # Create network
    docker.create_network()

    # Start proxy containers
    results = docker.run_batch(
        session_files=[str(f) for f in session_files],
        prefix="tokenade",
    )

    for r in results:
        status = "✅" if r["status"] == "running" else "❌"
        print(f"   {status} {r['name']} (port {r['port']})")

    # Start API server if requested
    if not args.no_api:
        print(f"\n🌐 Starting API server on port {args.api_port}...")
        import subprocess
        try:
            subprocess.run([
                "docker", "run", "-d",
                "--name", "tokenade-api",
                "-p", f"{args.api_port}:9224",
                "-v", f"{sessions_dir.absolute()}:/app/sessions",
                "-e", "TOKENADE_DATA_DIR=/app",
                "-e", "PYTHONUNBUFFERED=1",
                docker.image_name,
                "python", "-c",
                "from tokenade.core.api.server import TokenadeAPIServer; import asyncio; s=TokenadeAPIServer(); asyncio.run(s.start())",
            ], capture_output=True, text=True, check=True, timeout=30)
            print(f"   ✅ API server started")
        except Exception as e:
            print(f"   ❌ API server failed: {e}")

    print(f"\n{'=' * 60}\n")


def _container_stop(args):
    """Stop containers."""
    from tokenade.core.integration.docker_manager import DockerSessionManager

    docker = DockerSessionManager()
    if not docker.is_available():
        print("❌ Docker is not available")
        return

    name = getattr(args, "name", None)
    if name:
        if docker.stop_container(name):
            print(f"✅ Stopped {name}")
        else:
            print(f"❌ Failed to stop {name}")
    else:
        count = docker.cleanup(remove_all=False)
        print(f"✅ Stopped {count} container(s)")


def _container_restart(args):
    """Restart containers."""
    from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

    orch = ContainerOrchestrator()
    health_list = orch.check_all_health()

    for h in health_list:
        if orch.restart_container(h.name):
            print(f"✅ Restarted {h.name}")
        else:
            print(f"❌ Failed to restart {h.name}")


def _container_status(args):
    """Show container status."""
    from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

    orch = ContainerOrchestrator()
    summary = orch.get_status_summary()

    print("\n" + "=" * 60)
    print("TOKENADE - Container Status")
    print("=" * 60)
    print(f"\n📊 Total: {summary['total']} | Healthy: {summary['healthy']} | Unhealthy: {summary['unhealthy']} | Stopped: {summary['stopped']}")

    for c in summary["containers"]:
        icon = "🟢" if c["healthy"] else ("🔴" if c["status"] == "running" else "⚫")
        print(f"\n   {icon} {c['name']}")
        print(f"      Status: {c['status']}")
        print(f"      Restarts: {c['restart_count']}")
        if c["error"]:
            print(f"      Error: {c['error']}")

    print(f"\n{'=' * 60}\n")


def _container_logs(args):
    """Tail container logs."""
    import subprocess

    cmd = ["docker", "logs", "--tail", str(args.tail)]
    if args.follow:
        cmd.append("-f")
    cmd.append(args.name)

    try:
        subprocess.run(cmd, timeout=30)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ Failed to get logs: {e}")


def _container_refresh(args):
    """Refresh sessions inside a container."""
    from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

    orch = ContainerOrchestrator()
    results = orch.refresh_all_in_container(args.name, args.sessions_dir)

    for r in results:
        if r.get("success"):
            print(f"✅ {r.get('session', 'unknown')}: refreshed")
        else:
            print(f"❌ {r.get('session', 'unknown')}: {r.get('error', 'failed')}")


def _container_scale(args):
    """Scale proxy containers."""
    from tokenade.core.integration.docker_manager import DockerSessionManager
    from pathlib import Path

    docker = DockerSessionManager()
    if not docker.is_available():
        print("❌ Docker is not available")
        return

    sessions_dir = Path(args.sessions_dir)
    session_files = list(sessions_dir.glob("*.tokenade"))[:args.replicas]

    if not session_files:
        print(f"❌ No .tokenade files found")
        return

    # Stop existing
    docker.cleanup(remove_all=False)

    # Start new batch
    results = docker.run_batch(
        session_files=[str(f) for f in session_files],
        prefix="tokenade",
    )

    running = sum(1 for r in results if r["status"] == "running")
    print(f"✅ Scaled to {running}/{args.replicas} containers")


def _container_cleanup(args):
    """Stop and remove all tokenade containers."""
    from tokenade.core.integration.docker_manager import DockerSessionManager

    docker = DockerSessionManager()
    if not docker.is_available():
        print("❌ Docker is not available")
        return

    count = docker.cleanup(remove_all=True)
    print(f"✅ Cleaned up {count} container(s)")


def _container_health(args):
    """Check container health."""
    from tokenade.core.integration.container_orchestrator import ContainerOrchestrator

    orch = ContainerOrchestrator()

    if args.watch:
        print(f"🔍 Monitoring containers (interval: {args.interval}s, max restarts: {args.max_restarts})")
        print("   Press Ctrl+C to stop\n")
        try:
            orch.auto_restart_unhealthy(
                max_restarts=args.max_restarts,
                check_interval=args.interval,
            )
        except KeyboardInterrupt:
            orch.stop()
            print("\n✅ Monitor stopped")
    else:
        summary = orch.get_status_summary()
        print(f"\n📊 {summary['total']} containers: {summary['healthy']} healthy, {summary['unhealthy']} unhealthy")
        for c in summary["containers"]:
            icon = "🟢" if c["healthy"] else "🔴"
            print(f"   {icon} {c['name']} — {c['status']}")


def _container_generate(args):
    """Generate docker-compose override."""
    from tokenade.core.integration.container_orchestrator import generate_compose_override
    from pathlib import Path

    sessions_dir = Path(args.sessions_dir)
    session_files = [f.name for f in sessions_dir.glob("*.tokenade")]

    if not session_files:
        print(f"❌ No .tokenade files found in {sessions_dir}")
        return

    yaml_content = generate_compose_override(
        sessions=session_files,
        base_port=args.base_port,
    )

    if args.output:
        Path(args.output).write_text(yaml_content)
        print(f"✅ Generated {args.output}")
    else:
        print(yaml_content)


# ---------------------------------------------------------------------------
# Kubernetes management commands
# ---------------------------------------------------------------------------

def cmd_k8s(args):
    """Kubernetes deployment management."""
    action = getattr(args, "k8s_action", None)

    if action == "deploy":
        _k8s_deploy(args)
    elif action == "status":
        _k8s_status(args)
    elif action == "scale":
        _k8s_scale(args)
    elif action == "logs":
        _k8s_logs(args)
    elif action == "delete":
        _k8s_delete(args)
    elif action == "pods":
        _k8s_pods(args)
    else:
        print("Usage: tokenade k8s {deploy|status|scale|logs|delete|pods}")


def _k8s_deploy(args):
    """Generate and apply K8s manifests."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(
        namespace=args.namespace,
        image=args.image,
        replicas=args.replicas,
        port=args.port,
    )
    k8s = KubernetesManager(config)

    deployment_yaml = k8s.generate_deployment_yaml()
    service_yaml = k8s.generate_service_yaml()
    full_yaml = deployment_yaml + "\n---\n" + service_yaml

    if args.dry_run or args.output:
        if args.output:
            Path(args.output).write_text(full_yaml)
            print(f"✅ Generated {args.output}")
        else:
            print(full_yaml)
        return

    print("\n🚀 Deploying to Kubernetes...")
    if k8s.apply_manifests(full_yaml):
        print("✅ Applied successfully")
    else:
        print("❌ Failed to apply manifests")


def _k8s_status(args):
    """Show deployment status."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    status = k8s.get_deployment_status()
    if not status.get("available"):
        print(f"❌ {status.get('error', 'Deployment not found')}")
        return

    print(f"\n📊 Deployment: {status['name']}")
    print(f"   Replicas: {status['ready_replicas']}/{status['replicas']} ready")
    for c in status.get("conditions", []):
        print(f"   {c['type']}: {c['status']} — {c['message']}")


def _k8s_scale(args):
    """Scale deployment."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    if k8s.scale_deployment(args.replicas):
        print(f"✅ Scaled to {args.replicas} replicas")
    else:
        print("❌ Failed to scale")


def _k8s_logs(args):
    """Tail pod logs."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    pods = k8s.get_pods()
    for pod in pods:
        print(f"\n--- {pod['name']} ---")
        logs = k8s.get_logs(pod["name"], tail=args.tail)
        print(logs)


def _k8s_delete(args):
    """Delete deployment and service."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    if k8s.delete_deployment():
        print("✅ Deleted deployment and service")
    else:
        print("❌ Failed to delete")


def _k8s_pods(args):
    """List pods."""
    from tokenade.core.integration.kubernetes import KubernetesManager, KubernetesConfig

    config = KubernetesConfig(namespace=args.namespace)
    k8s = KubernetesManager(config)

    pods = k8s.get_pods()
    if not pods:
        print("No pods found")
        return

    for pod in pods:
        status_icon = "🟢" if pod["status"] == "Running" else "🔴"
        print(f"   {status_icon} {pod['name']} — {pod['status']} (restarts: {pod['restart_count']})")
