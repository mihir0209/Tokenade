"""
Container CLI command.

Manage Tokenade in Docker containers.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from tokenade.cli.output import heading


def cmd_container(args: argparse.Namespace) -> None:
    """Container management commands."""
    if args.container_command == "build":
        _container_build(args)
    elif args.container_command == "run":
        _container_run(args)
    elif args.container_command == "stop":
        _container_stop(args)
    elif args.container_command == "status":
        _container_status(args)
    elif args.container_command == "logs":
        _container_logs(args)
    elif args.container_command == "shell":
        _container_shell(args)
    else:
        print(f"Unknown container command: {args.container_command}")
        sys.exit(1)


def _container_build(args: argparse.Namespace) -> None:
    """Build Docker image."""
    heading("Building Tokenade Docker Image")

    dockerfile = Path(args.dockerfile) if args.dockerfile else Path("Dockerfile")
    if not dockerfile.exists():
        print(f"[ERROR] Dockerfile not found: {dockerfile}")
        sys.exit(1)

    tag = args.tag or "tokenade:latest"
    cmd = ["docker", "build", "-t", tag, "-f", str(dockerfile), "."]

    if args.no_cache:
        cmd.append("--no-cache")

    print(f" Building image: {tag}")
    print(f"[DIR] Context: {Path('.').absolute()}")

    try:
        result = subprocess.run(cmd, check=True)
        print(f"\n[OK] Image built successfully: {tag}")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Build failed: {e}")
        sys.exit(1)


def _container_run(args: argparse.Namespace) -> None:
    """Run Tokenade in a container."""
    heading("Running Tokenade Container")

    image = args.image or "tokenade:latest"
    tag = args.tag or "tokenade-run"

    cmd = [
        "docker", "run", "-d",
        "--name", tag,
    ]

    # Volume mounts
    if args.sessions_dir:
        cmd.extend(["-v", f"{args.sessions_dir}:/home/tokenade/.tokenade/sessions"])

    if args.plugins_dir:
        cmd.extend(["-v", f"{args.plugins_dir}:/home/tokenade/.tokenade/plugins"])

    # Port mapping
    if args.port:
        cmd.extend(["-p", f"{args.port}:{args.port}"])

    # Environment variables
    if args.env:
        for env_var in args.env:
            cmd.extend(["-e", env_var])

    # Command
    cmd.append(image)
    if args.command:
        cmd.extend(args.command)

    print(f" Running container: {tag}")
    print(f"[PKG] Image: {image}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"\n[OK] Container started: {tag}")
        print(f"   ID: {result.stdout.strip()[:12]}")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Failed to start container: {e}")
        sys.exit(1)


def _container_stop(args: argparse.Namespace) -> None:
    """Stop a running container."""
    heading("Stopping Tokenade Container")

    container = args.container
    cmd = ["docker", "stop", container]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[OK] Container stopped: {container}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to stop container: {e}")
        sys.exit(1)


def _container_status(args: argparse.Namespace) -> None:
    """Show container status."""
    heading("Tokenade Container Status")

    cmd = ["docker", "ps", "-a", "--filter", "name=tokenade", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to get status: {e}")
        sys.exit(1)


def _container_logs(args: argparse.Namespace) -> None:
    """Show container logs."""
    container = args.container
    cmd = ["docker", "logs", "--tail", str(args.tail), container]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to get logs: {e}")
        sys.exit(1)


def _container_shell(args: argparse.Namespace) -> None:
    """Open shell in container."""
    container = args.container
    cmd = ["docker", "exec", "-it", container, "/bin/bash"]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to open shell: {e}")
        sys.exit(1)


def register_container_command(subparsers: argparse._SubParsersAction) -> None:
    """Register container command."""
    parser = subparsers.add_parser(
        "container",
        help="Manage Tokenade in Docker containers",
        description="Build, run, and manage Tokenade Docker containers",
    )

    container_subparsers = parser.add_subparsers(dest="container_command")

    # Build
    build_parser = container_subparsers.add_parser("build", help="Build Docker image")
    build_parser.add_argument("-t", "--tag", default="tokenade:latest", help="Image tag")
    build_parser.add_argument("-f", "--dockerfile", help="Dockerfile path")
    build_parser.add_argument("--no-cache", action="store_true", help="Build without cache")
    build_parser.set_defaults(func=cmd_container)

    # Run
    run_parser = container_subparsers.add_parser("run", help="Run container")
    run_parser.add_argument("-i", "--image", default="tokenade:latest", help="Docker image")
    run_parser.add_argument("-n", "--tag", default="tokenade-run", help="Container name")
    run_parser.add_argument("-s", "--sessions-dir", help="Sessions directory to mount")
    run_parser.add_argument("-p", "--plugins-dir", help="Plugins directory to mount")
    run_parser.add_argument("--port", type=int, help="Port to expose")
    run_parser.add_argument("-e", "--env", action="append", help="Environment variable")
    run_parser.add_argument("command", nargs="*", help="Command to run")
    run_parser.set_defaults(func=cmd_container)

    # Stop
    stop_parser = container_subparsers.add_parser("stop", help="Stop container")
    stop_parser.add_argument("container", help="Container name or ID")
    stop_parser.set_defaults(func=cmd_container)

    # Status
    status_parser = container_subparsers.add_parser("status", help="Show container status")
    status_parser.set_defaults(func=cmd_container)

    # Logs
    logs_parser = container_subparsers.add_parser("logs", help="Show container logs")
    logs_parser.add_argument("container", help="Container name or ID")
    logs_parser.add_argument("--tail", type=int, default=100, help="Number of lines to show")
    logs_parser.set_defaults(func=cmd_container)

    # Shell
    shell_parser = container_subparsers.add_parser("shell", help="Open shell in container")
    shell_parser.add_argument("container", help="Container name or ID")
    shell_parser.set_defaults(func=cmd_container)
