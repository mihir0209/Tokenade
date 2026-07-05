"""
CI/CD CLI commands — cicd, ci, autopsy.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("tokenade")


def cmd_cicd(args):
    """Generate CI/CD workflow files."""
    from tokenade.core.cicd.workflow_generator import (
        WorkflowConfig, WorkflowGenerator, generate_all_workflows,
    )

    print("\n" + "=" * 80)
    print("TOKENADE - CI/CD Workflow Generator")
    print("=" * 80)

    if args.generate_all:
        print(f"\n📂 Sessions directory: {args.sessions_dir}")
        print(f"⏰ Refresh interval: {args.interval_hours} hours")
        print(f"🌐 Source browser: {args.source_browser}")
        print(f"📁 Output directory: {args.output_dir}")

        workflows = generate_all_workflows(
            sessions_dir=args.sessions_dir,
            refresh_interval_hours=args.interval_hours,
            source_browser=args.source_browser,
            output_dir=args.output_dir,
        )

        print(f"\n✅ Generated {len(workflows)} workflow files:")
        for filename in workflows:
            print(f"   • {args.output_dir}/{filename}")

        print(f"\n📖 Next steps:")
        print(f"   1. Copy .github/workflows/ to your repository")
        print(f"   2. Add your .tokenade files to {args.sessions_dir}/")
        print(f"   3. Push to GitHub — workflows will run automatically")
        return

    if args.workflow_type == "github":
        config = WorkflowConfig(
            sessions_dir=args.sessions_dir,
            refresh_interval_hours=args.interval_hours,
            source_browser=args.source_browser,
        )
        generator = WorkflowGenerator()
        workflow = generator.generate_github_actions(config)
        output_path = args.output or ".github/workflows/refresh-sessions.yml"
        generator.save(workflow, output_path)
        print(f"\n✅ Generated GitHub Actions workflow: {output_path}")

    elif args.workflow_type == "gitlab":
        config = WorkflowConfig(
            sessions_dir=args.sessions_dir,
            refresh_interval_hours=args.interval_hours,
            source_browser=args.source_browser,
        )
        generator = WorkflowGenerator()
        workflow = generator.generate_gitlab_ci(config)
        output_path = args.output or ".gitlab-ci.yml"
        generator.save(workflow, output_path)
        print(f"\n✅ Generated GitLab CI pipeline: {output_path}")

    elif args.workflow_type == "cron":
        config = WorkflowConfig(
            sessions_dir=args.sessions_dir,
            refresh_interval_hours=args.interval_hours,
            source_browser=args.source_browser,
        )
        generator = WorkflowGenerator()
        script = generator.generate_cron_script(config)
        output_path = args.output or f"{args.sessions_dir}/refresh.sh"
        generator.save(script, output_path)
        print(f"\n✅ Generated cron script: {output_path}")
        print(f"\n📖 Add to crontab:")
        print(f"   0 */{args.interval_hours} * * * {output_path}")


def cmd_ci(args):
    """Session CI runner — read tokenade.yml and run validation."""
    from tokenade.core.cicd.runner import (
        CIConfig, CIRunner, DEFAULT_TEMPLATE,
    )

    ci_action = getattr(args, "ci_action", "run")

    if ci_action == "init":
        config_path = getattr(args, "config", "tokenade.yml")
        if os.path.exists(config_path):
            print(f"❌ {config_path} already exists")
            return
        with open(config_path, "w") as f:
            f.write(DEFAULT_TEMPLATE)
        print(f"✅ Created {config_path}")
        print("   Edit the file, then run: tokenade ci run")
        return

    if ci_action == "validate":
        config_path = getattr(args, "config", "tokenade.yml")
        try:
            config = CIConfig.from_file(config_path)
            errors = config.validate_config()
            if errors:
                print(f"❌ Config has {len(errors)} error(s):")
                for e in errors:
                    print(f"   • {e}")
            else:
                print(f"✅ Config is valid ({len(config.sessions)} sessions)")
        except FileNotFoundError:
            print(f"❌ Config not found: {config_path}")
        except Exception as e:
            print(f"❌ Config error: {e}")
        return

    if ci_action == "lint":
        config_path = getattr(args, "config", "tokenade.yml")
        try:
            config = CIConfig.from_file(config_path)
            errors = config.validate_config()
            if errors:
                for e in errors:
                    print(f"ERROR: {e}")

            for entry in config.sessions:
                session_path = os.path.join(".", entry.file)
                if not os.path.exists(session_path):
                    print(f"WARN: {entry.name}: file not found: {entry.file}")
                if entry.health_threshold > 90:
                    print(
                        f"WARN: {entry.name}: health_threshold "
                        f"{entry.health_threshold}% is very high"
                    )
            if not errors:
                print(f"Lint passed ({len(config.sessions)} sessions)")
        except Exception as e:
            print(f"ERROR: {e}")
        return

    # Default: run
    config_path = getattr(args, "config", "tokenade.yml")
    try:
        config = CIConfig.from_file(config_path)
    except FileNotFoundError:
        print(f"❌ Config not found: {config_path}")
        print("   Create one with: tokenade ci init")
        return
    except Exception as e:
        print(f"❌ Config error: {e}")
        return

    errors = config.validate_config()
    if errors:
        print(f"❌ Config has {len(errors)} error(s):")
        for e in errors:
            print(f"   • {e}")
        return

    fmt = getattr(args, "format", None)
    if fmt:
        config.output.format = fmt

    runner = CIRunner(config, base_dir=".")
    report = runner.run()
    report.config_path = config_path

    if config.output.format == "json":
        output = report.to_json()
    elif config.output.format == "junit":
        output = report.to_junit()
    else:
        output = report.to_text()

    print(output)

    if config.output.path:
        out_path = Path(config.output.path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write(output)
        print(f"\n  📄 Report saved: {config.output.path}")

    if report.overall_status == "fail":
        if config.on_failure.action == "webhook" and config.on_failure.webhook:
            _send_ci_webhook(config.on_failure.webhook, report)

    sys.exit(report.exit_code)


def _send_ci_webhook(url: str, report):
    """Send CI failure notification to webhook."""
    try:
        import requests
        payload = {
            "text": (
                f"Tokenade CI: {report.overall_status.upper()} — "
                f"{report.failed}/{len(report.session_results)} sessions failed"
            ),
        }
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass


def cmd_autopsy(args):
    """Session forensics — analyze why a session died."""
    from tokenade.core.forensics.autopsy import SessionAutopsy

    session_file = args.session
    if not session_file:
        print("❌ Specify session: tokenade autopsy -s <session.tokenade>")
        return

    if not os.path.exists(session_file):
        print(f"❌ File not found: {session_file}")
        return

    autopsy = SessionAutopsy(session_file)
    report = autopsy.analyze()

    fmt = getattr(args, "format", "text")
    if fmt == "json":
        print(report.to_json())
    else:
        print(report.to_text())

    compare_file = getattr(args, "compare", None)
    if compare_file and os.path.exists(compare_file):
        print("\n" + "=" * 60)
        print("COMPARISON")
        print("=" * 60)
        autopsy2 = SessionAutopsy(compare_file)
        report2 = autopsy2.analyze()

        print(f"  Dead session:    {report.cause_of_death} "
              f"({report.confidence})")
        print(f"  Compare session: {report2.cause_of_death} "
              f"({report2.confidence})")
        print(f"  Dead cookies: {report.cookie_count} "
              f"({report.expired_count} expired)")
        print(f"  Compare cookies: {report2.cookie_count} "
              f"({report2.expired_count} expired)")

        dead_crits = {
            e.name for e in report.cookie_evidence if e.is_critical
        }
        cmp_crits = {
            e.name for e in report2.cookie_evidence if e.is_critical
        }
        missing_in_dead = cmp_crits - dead_crits
        extra_in_dead = dead_crits - cmp_crits

        if missing_in_dead:
            print(f"  Missing in dead: {', '.join(missing_in_dead)}")
        if extra_in_dead:
            print(f"  Extra in dead: {', '.join(extra_in_dead)}")


def cmd_cloak(args):
    """CloakBrowser stealth browser management."""
    from tokenade.core.browser.stealth.cloak import (
        CloakBrowserBackend,
        is_cloakbrowser_available,
        get_binary_info,
        ensure_binary,
    )

    cloak_action = getattr(args, "cloak_action", "info")

    if cloak_action == "info":
        info = get_binary_info()
        json_output = getattr(args, "json_output", False)
        if json_output:
            print(json.dumps(info, indent=2))
        else:
            print("\n" + "=" * 60)
            print("CLOAKBROWSER STATUS")
            print("=" * 60)
            print(f"  Package installed: {'Yes' if is_cloakbrowser_available() else 'No'}")
            print(f"  Binary installed:  {'Yes' if info.get('installed') else 'No'}")
            if info.get("version"):
                print(f"  Binary version:    {info['version']}")
            if info.get("platform"):
                print(f"  Platform:          {info['platform']}")
            if info.get("tier"):
                print(f"  License tier:      {info['tier']}")
            if info.get("binary_path"):
                print(f"  Binary path:       {info['binary_path']}")
            if info.get("download_url"):
                print(f"  Download URL:      {info['download_url']}")
            if info.get("error"):
                print(f"  Error:             {info['error']}")
            print("=" * 60)
            print()

    elif cloak_action == "install":
        if not is_cloakbrowser_available():
            print("❌ cloakbrowser package not installed")
            print("   Install with: pip install cloakbrowser")
            return
        print("Downloading CloakBrowser binary...")
        if ensure_binary():
            info = get_binary_info()
            print(f"✅ CloakBrowser installed: v{info.get('version', '?')}")
            print(f"   Platform: {info.get('platform', '?')}")
            print(f"   Tier: {info.get('tier', '?')}")
        else:
            print("❌ Failed to download CloakBrowser binary")

    elif cloak_action == "serve":
        if not is_cloakbrowser_available():
            print("❌ cloakbrowser package not installed")
            return
        port = getattr(args, "port", 9222)
        proxy = getattr(args, "proxy", None)
        headless = not getattr(args, "visible", False)
        idle_timeout = getattr(args, "idle_timeout", None)

        print(f"Starting CloakBrowser CDP server on port {port}...")
        backend = CloakBrowserBackend()
        try:
            proc = backend.serve_cdp(
                port=port,
                proxy=proxy,
                headless=headless,
                idle_timeout=idle_timeout,
            )
            print(f"✅ CloakBrowser CDP server running on port {port}")
            print(f"   PID: {proc.pid}")
            print(f"   Connect: http://127.0.0.1:{port}")
            print()
            print("   Press Ctrl+C to stop")
            try:
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
                print("\nStopped.")
        except Exception as e:
            print(f"❌ Failed to start server: {e}")

    else:
        print("Usage: tokenade cloak {info|install|serve}")


def cmd_tui(args):
    """Launch interactive terminal UI."""
    from tokenade.tui import run_tui, _check_textual

    if not _check_textual():
        print("TUI requires textual: pip install 'tokenade[tui]'")
        print("Or use: tokenade plugin browse (static HTML)")
        return

    mode = getattr(args, "tui_mode", "full")
    run_tui(mode=mode)
