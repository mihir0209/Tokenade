"""Tests for CI/CD workflow generator."""
import pytest
from pathlib import Path

from tokenade.core.cicd.workflow_generator import (
    WorkflowConfig,
    WorkflowGenerator,
    generate_all_workflows,
)


class TestWorkflowConfig:
    def test_default_config(self):
        config = WorkflowConfig()
        assert config.sessions_dir == "sessions/"
        assert config.refresh_interval_hours == 6
        assert config.source_browser == "firefox"
        assert config.python_version == "3.12"
        assert config.max_retries == 3

    def test_custom_config(self):
        config = WorkflowConfig(
            sessions_dir="my-sessions/",
            refresh_interval_hours=12,
            source_browser="chrome",
            python_version="3.11",
        )
        assert config.sessions_dir == "my-sessions/"
        assert config.refresh_interval_hours == 12
        assert config.source_browser == "chrome"
        assert config.python_version == "3.11"


class TestWorkflowGenerator:
    def test_generate_github_actions(self):
        generator = WorkflowGenerator()
        config = WorkflowConfig(sessions_dir="sessions/", refresh_interval_hours=6)
        workflow = generator.generate_github_actions(config)

        assert "name: Tokenade Session Refresh" in workflow
        assert "cron: '0 */6 * * *'" in workflow
        assert "pip install tokenade" in workflow
        assert "tokenade refresh-oauth" in workflow
        assert "tokenade refresh" in workflow
        assert "tokenade health" in workflow
        assert "git config user.name" in workflow

    def test_generate_github_actions_custom_interval(self):
        generator = WorkflowGenerator()
        config = WorkflowConfig(refresh_interval_hours=12)
        workflow = generator.generate_github_actions(config)
        assert "cron: '0 */12 * * *'" in workflow

    def test_generate_gitlab_ci(self):
        generator = WorkflowGenerator()
        config = WorkflowConfig(sessions_dir="sessions/")
        pipeline = generator.generate_gitlab_ci(config)

        assert "stages:" in pipeline
        assert "refresh-sessions:" in pipeline
        assert "health-check:" in pipeline
        assert "pip install tokenade" in pipeline

    def test_generate_cron_script(self):
        generator = WorkflowGenerator()
        config = WorkflowConfig(sessions_dir="sessions/", refresh_interval_hours=6)
        script = generator.generate_cron_script(config)

        assert "#!/usr/bin/env bash" in script
        assert "MAX_RETRIES=3" in script
        assert "tokenade refresh-oauth" in script
        assert "tokenade refresh" in script
        assert "tokenade health" in script

    def test_generate_docker_cron(self):
        generator = WorkflowGenerator()
        config = WorkflowConfig(sessions_dir="sessions/", refresh_interval_hours=6)
        dockerfile = generator.generate_docker_cron(config)

        assert "FROM python:3.12-slim" in dockerfile
        assert "pip install" in dockerfile
        assert "tokenade" in dockerfile
        assert "refresh.sh" in dockerfile

    def test_save_workflow(self, tmp_path):
        generator = WorkflowGenerator()
        output_file = tmp_path / "workflow.yml"
        generator.save("test content", str(output_file))
        assert output_file.read_text() == "test content"


class TestGenerateAllWorkflows:
    def test_generate_all(self, tmp_path):
        output_dir = tmp_path / "ci"
        workflows = generate_all_workflows(
            sessions_dir="sessions/",
            refresh_interval_hours=6,
            output_dir=str(output_dir),
        )

        assert "github-actions.yml" in workflows
        assert "gitlab-ci.yml" in workflows
        assert "refresh.sh" in workflows
        assert "Dockerfile" in workflows

        assert (output_dir / "github-actions.yml").exists()
        assert (output_dir / "gitlab-ci.yml").exists()
        assert (output_dir / "refresh.sh").exists()
        assert (output_dir / "Dockerfile").exists()

    def test_generate_all_custom(self, tmp_path):
        output_dir = tmp_path / "custom_ci"
        workflows = generate_all_workflows(
            sessions_dir="my-sessions/",
            refresh_interval_hours=12,
            source_browser="chrome",
            output_dir=str(output_dir),
        )

        assert "my-sessions/" in workflows["github-actions.yml"]
        assert "0 */12 * * *" in workflows["github-actions.yml"]
        assert "chrome" in workflows["github-actions.yml"]
