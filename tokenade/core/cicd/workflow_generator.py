"""
CI/CD Workflow Generator for Tokenade.

Generates GitHub Actions, GitLab CI, and cron-based workflows for:
- Automated session refresh (OAuth token renewal)
- Multi-account batch refresh
- Health monitoring with alerts
- Session file commit-back to repository

Usage:
    generator = WorkflowGenerator()
    workflow = generator.generate_github_actions(
        sessions_dir="sessions/",
        refresh_interval_hours=6,
    )
    generator.save(workflow, ".github/workflows/refresh-sessions.yml")
"""


import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkflowConfig:
    """Configuration for a CI/CD workflow."""
    sessions_dir: str = "sessions/"
    refresh_interval_hours: int = 6
    source_browser: str = "firefox"
    source_profile: Optional[str] = None
    health_check: bool = True
    auto_commit: bool = True
    commit_message: str = "chore: auto-refresh tokenade sessions"
    python_version: str = "3.12"
    tokenade_version: str = "latest"
    notify_on_failure: bool = False
    notification_webhook: str = ""
    max_retries: int = 3
    timeout_minutes: int = 10


class WorkflowGenerator:
    """
    Generates CI/CD workflow files for automated session refresh.

    Usage:
        generator = WorkflowGenerator()
        workflow = generator.generate_github_actions(config)
        generator.save(workflow, ".github/workflows/refresh-sessions.yml")
    """

    def generate_github_actions(self, config: Optional[WorkflowConfig] = None) -> str:
        """
        Generate a GitHub Actions workflow for session refresh.

        Returns:
            YAML workflow string
        """
        config = config or WorkflowConfig()

        workflow = f"""name: Tokenade Session Refresh

on:
  schedule:
    - cron: '0 */{config.refresh_interval_hours} * * *'
  workflow_dispatch:
    inputs:
      force_refresh:
        description: 'Force refresh all sessions'
        required: false
        default: 'false'
        type: boolean

permissions:
  contents: write

jobs:
  refresh-sessions:
    runs-on: ubuntu-latest
    timeout-minutes: {config.timeout_minutes}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Python {config.python_version}
        uses: actions/setup-python@v5
        with:
          python-version: '{config.python_version}'

      - name: Install Tokenade
        run: pip install tokenade{'' if config.tokenade_version == 'latest' else f'=={config.tokenade_version}'}

      - name: Refresh sessions
        run: |
          echo "=== Tokenade Session Refresh ==="
          echo "Time: $(date -u)"

          FAILED=0
          SUCCESS=0
          SKIPPED=0

          for f in {config.sessions_dir}*.tokenade; do
            [ -f "$f" ] || continue

            echo ""
            echo "--- Processing: $f ---"

            # Check if OAuth config exists
            HAS_OAUTH=$(python3 -c "
          import json, sys
          with open('$f') as fh:
              s = json.load(fh)
          sys.exit(0 if s.get('oauth_config') else 1)
          " 2>/dev/null && echo "yes" || echo "no")

            if [ "$HAS_OAUTH" = "yes" ]; then
              # OAuth token refresh
              echo "  Using OAuth token refresh..."
              if tokenade refresh-oauth -s "$f"; then
                echo "  ✓ OAuth refresh succeeded"
                SUCCESS=$((SUCCESS + 1))
              else
                echo "  ✗ OAuth refresh failed"
                FAILED=$((FAILED + 1))
              fi
            else
              # Cookie re-export from source browser
              echo "  Using cookie re-export..."
              if tokenade refresh -s "$f" --source-browser {config.source_browser}{" --source-profile " + config.source_profile if config.source_profile else ""}; then
                echo "  ✓ Cookie refresh succeeded"
                SUCCESS=$((SUCCESS + 1))
              else
                echo "  ✗ Cookie refresh failed"
                FAILED=$((FAILED + 1))
              fi
            fi
          done

          echo ""
          echo "=== Summary ==="
          echo "Success: $SUCCESS"
          echo "Failed: $FAILED"
          echo "Skipped: $SKIPPED"

          # Run health check if enabled
          if [ {str(config.health_check).lower()} = "true" ]; then
            echo ""
            echo "=== Health Check ==="
            for f in {config.sessions_dir}*.tokenade; do
              [ -f "$f" ] || continue
              echo "--- $f ---"
              tokenade health -s "$f" || true
            done
          fi

          # Exit with error if any refresh failed
          if [ $FAILED -gt 0 ]; then
            echo ""
            echo "ERROR: $FAILED session(s) failed to refresh"
            exit 1
          fi

      - name: Commit updated sessions
        if: {str(config.auto_commit).lower()}
        run: |
          git config user.name "tokenade-bot"
          git config user.email "bot@tokenade.dev"
          git add {config.sessions_dir}*.tokenade
          git diff --staged --quiet || git commit -m "{config.commit_message}"
          git push
"""
        return workflow

    def generate_gitlab_ci(self, config: Optional[WorkflowConfig] = None) -> str:
        """
        Generate a GitLab CI/CD pipeline for session refresh.

        Returns:
            .gitlab-ci.yml string
        """
        config = config or WorkflowConfig()

        pipeline = f"""stages:
  - refresh
  - health-check

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.pip-cache"

cache:
  paths:
    - .pip-cache/

refresh-sessions:
  stage: refresh
  image: python:{config.python_version}-slim
  timeout: {config.timeout_minutes}m
  script:
    - pip install tokenade{'' if config.tokenade_version == 'latest' else f'=={config.tokenade_version}'}
    - |
      echo "=== Tokenade Session Refresh ==="
      FAILED=0
      SUCCESS=0

      for f in {config.sessions_dir}*.tokenade; do
        [ -f "$f" ] || continue
        echo "--- Processing: $f ---"

        HAS_OAUTH=$(python3 -c "
      import json, sys
      with open('$f') as fh:
          s = json.load(fh)
      sys.exit(0 if s.get('oauth_config') else 1)
      " 2>/dev/null && echo "yes" || echo "no")

        if [ "$HAS_OAUTH" = "yes" ]; then
          if tokenade refresh-oauth -s "$f"; then
            SUCCESS=$((SUCCESS + 1))
          else
            FAILED=$((FAILED + 1))
          fi
        else
          if tokenade refresh -s "$f" --source-browser {config.source_browser}; then
            SUCCESS=$((SUCCESS + 1))
          else
            FAILED=$((FAILED + 1))
          fi
        fi
      done

      echo "Success: $SUCCESS, Failed: $FAILED"
      [ $FAILED -eq 0 ]
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
    - if: $CI_PIPELINE_SOURCE == "web"

  artifacts:
    paths:
      - {config.sessions_dir}*.tokenade
    expire_in: 7 days

health-check:
  stage: health-check
  image: python:{config.python_version}-slim
  script:
    - pip install tokenade
    - |
      for f in {config.sessions_dir}*.tokenade; do
        [ -f "$f" ] || continue
        tokenade health -s "$f"
      done
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
"""
        return pipeline

    def generate_cron_script(self, config: Optional[WorkflowConfig] = None) -> str:
        """
        Generate a bash script for cron-based refresh.

        Returns:
            Bash script string
        """
        config = config or WorkflowConfig()

        script = f"""#!/usr/bin/env bash
# Tokenade Session Refresh Script
# Generated by tokenade CI/CD workflow generator
#
# Add to crontab:
#   0 */{config.refresh_interval_hours} * * * {config.sessions_dir}/refresh.sh
#
# Or run manually:
#   bash {config.sessions_dir}/refresh.sh

set -euo pipefail

SESSIONS_DIR="{config.sessions_dir}"
SOURCE_BROWSER="{config.source_browser}"
LOG_FILE="{config.sessions_dir}/refresh.log"
MAX_RETRIES={config.max_retries}

log() {{
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}}

refresh_session() {{
    local file="$1"
    local attempt=1

    while [ $attempt -le $MAX_RETRIES ]; do
        log "Attempt $attempt/$MAX_RETRIES for $file"

        # Check for OAuth config
        HAS_OAUTH=$(python3 -c "
import json, sys
with open('$file') as f:
    s = json.load(f)
sys.exit(0 if s.get('oauth_config') else 1)
" 2>/dev/null && echo "yes" || echo "no")

        if [ "$HAS_OAUTH" = "yes" ]; then
            if tokenade refresh-oauth -s "$file" 2>>"$LOG_FILE"; then
                log "✓ OAuth refresh succeeded: $file"
                return 0
            fi
        else
            if tokenade refresh -s "$file" --source-browser "$SOURCE_BROWSER" 2>>"$LOG_FILE"; then
                log "✓ Cookie refresh succeeded: $file"
                return 0
            fi
        fi

        attempt=$((attempt + 1))
        sleep 10
    done

    log "✗ Failed to refresh: $file (after $MAX_RETRIES attempts)"
    return 1
}}

log "=== Session Refresh Started ==="

FAILED=0
SUCCESS=0

for f in "$SESSIONS_DIR"/*.tokenade; do
    [ -f "$f" ] || continue

    if refresh_session "$f"; then
        SUCCESS=$((SUCCESS + 1))
    else
        FAILED=$((FAILED + 1))
    fi
done

log "=== Summary: Success=$SUCCESS, Failed=$FAILED ==="

# Health check
log "=== Health Check ==="
for f in "$SESSIONS_DIR"/*.tokenade; do
    [ -f "$f" ] || continue
    tokenade health -s "$f" 2>>"$LOG_FILE" || true
done

if [ $FAILED -gt 0 ]; then
    log "ERROR: $FAILED session(s) failed"
    exit 1
fi
"""
        return script

    def generate_docker_cron(self, config: Optional[WorkflowConfig] = None) -> str:
        """
        Generate a Dockerfile for cron-based refresh.

        Returns:
            Dockerfile string
        """
        config = config or WorkflowConfig()

        dockerfile = f"""FROM python:{config.python_version}-slim

WORKDIR /app

RUN pip install --no-cache-dir tokenade

COPY {config.sessions_dir} /app/sessions/
COPY refresh.sh /app/refresh.sh
RUN chmod +x /app/refresh.sh

# Run every {config.refresh_interval_hours} hours
CMD ["sh", "-c", "while true; do /app/refresh.sh; sleep $(( {config.refresh_interval_hours} * 3600 )); done"]
"""
        return dockerfile

    def save(self, content: str, output_path: str):
        """Save generated content to file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Workflow saved: {path}")


def generate_all_workflows(
    sessions_dir: str = "sessions/",
    refresh_interval_hours: int = 6,
    source_browser: str = "firefox",
    output_dir: str = ".tokenade/ci",
) -> Dict[str, str]:
    """
    Generate all CI/CD workflow files.

    Args:
        sessions_dir: Directory containing .tokenade files
        refresh_interval_hours: How often to refresh (hours)
        source_browser: Source browser for cookie re-export
        output_dir: Directory to save workflow files

    Returns:
        Dict of filename -> content
    """
    config = WorkflowConfig(
        sessions_dir=sessions_dir,
        refresh_interval_hours=refresh_interval_hours,
        source_browser=source_browser,
    )

    generator = WorkflowGenerator()
    workflows = {
        "github-actions.yml": generator.generate_github_actions(config),
        "gitlab-ci.yml": generator.generate_gitlab_ci(config),
        "refresh.sh": generator.generate_cron_script(config),
        "Dockerfile": generator.generate_docker_cron(config),
    }

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for filename, content in workflows.items():
        filepath = output_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Generated: {filepath}")

    return workflows
