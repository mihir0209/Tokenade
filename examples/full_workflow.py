#!/usr/bin/env python3
"""
Example 2: Full Workflow - Export, Package, and Proxy

Demonstrates the complete workflow:
1. Export cookies from a browser
2. Package into .tokenade format with TLS profile
3. Start proxy server

Usage:
    python examples/full_workflow.py --browser firefox
"""

import sys
import json
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
from tokenade.core.importer.cookie_extractor import CookieExtractor


def export_session(browser: str, site_domains: list) -> dict:
    """Export session from browser."""
    print(f"\n1. Exporting from {browser}...")
    
    # Discover browser profile
    discovery = BrowserProfileDiscovery()
    profiles = discovery.discover_all()
    
    all_profiles = []
    for browser_profiles in profiles.values():
        all_profiles.extend(browser_profiles)
    
    matching = [p for p in all_profiles if p.browser == browser]
    if not matching:
        print(f"   No {browser} profiles found")
        return None
    
    profile_path = str(matching[0].path)
    print(f"   Found profile: {matching[0].name}")
    
    # Extract cookies
    extractor = CookieExtractor(profile_path, browser=browser)
    all_cookies = extractor.extract(site_filter=None)
    print(f"   Extracted {len(all_cookies)} total cookies")
    
    # Filter by domain
    filtered = []
    for cookie in all_cookies:
        domain = cookie.get("domain", "")
        for d in site_domains:
            if d.startswith("."):
                if domain.endswith(d) or domain == d[1:]:
                    filtered.append(cookie)
                    break
            else:
                if domain == d or domain.endswith("." + d):
                    filtered.append(cookie)
                    break
    
    print(f"   Filtered to {len(filtered)} cookies for target domains")
    
    return {
        "cookies": filtered,
        "browser": browser,
        "profile": matching[0].name
    }


def package_session(session_data: dict) -> dict:
    """Package session into .tokenade format."""
    print("\n2. Packaging session...")
    
    packager = SessionPackager()
    
    package = packager.package(
        cookies=session_data["cookies"],
        browser=session_data["browser"],
        profile=session_data["profile"],
        fingerprint=None  # Would collect from live browser in production
    )
    
    print(f"   Site: {package['site_name']}")
    print(f"   Auth: {package['auth_status']}")
    print(f"   Cookies: {len(package['cookies'])}")
    print(f"   TLS Profile: {package.get('tls_profile', {}).get('impersonate', 'auto')}")
    
    return package


def save_session(package: dict, output_path: str):
    """Save session to file."""
    print(f"\n3. Saving to {output_path}...")
    
    packager = SessionPackager()
    saved_path = packager.save(package, output_path)
    
    print(f"   Saved: {saved_path}")
    return saved_path


def start_proxy(package: dict, port: int):
    """Start proxy server."""
    print(f"\n4. Starting proxy on port {port}...")
    
    from tokenade.core.proxy.server import TokenadeProxy, ProxyConfig
    
    config = ProxyConfig(port=port, gui_mode=True)
    proxy = TokenadeProxy(package, config)
    
    print("\n" + "=" * 60)
    print("Proxy is running!")
    print("=" * 60)
    print(f"\nOpen http://127.0.0.1:{port} in your browser")
    print("\nOr configure HTTP proxy:")
    print(f"  export HTTP_PROXY=http://127.0.0.1:{port}")
    print(f"  export HTTPS_PROXY=http://127.0.0.1:{port}")
    print("\nPress Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    proxy.run()


def main():
    parser = argparse.ArgumentParser(description="Tokenade Full Workflow Example")
    parser.add_argument("--browser", "-b", default="firefox", 
                       choices=["chrome", "firefox", "edge", "brave"],
                       help="Browser to export from")
    parser.add_argument("--domains", "-d", nargs="+", 
                       default=[".github.com", "github.com"],
                       help="Domain filter")
    parser.add_argument("--port", "-p", type=int, default=9222,
                       help="Proxy port")
    parser.add_argument("--output", "-o", default="session.tokenade",
                       help="Output file")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Tokenade - Full Workflow Example")
    print("=" * 60)
    print(f"Browser: {args.browser}")
    print(f"Domains: {args.domains}")
    print(f"Port: {args.port}")
    
    # Step 1: Export
    session_data = export_session(args.browser, args.domains)
    if not session_data or not session_data["cookies"]:
        print("\nNo cookies found. Using sample session for demo...")
        
        # Create sample session for demo
        import time
        session_data = {
            "cookies": [
                {
                    "name": "user_session",
                    "value": "gho_sample123",
                    "domain": ".github.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                    "sameSite": "Lax",
                    "expires": int(time.time()) + 86400 * 7
                }
            ],
            "browser": args.browser,
            "profile": "default"
        }
    
    # Step 2: Package
    package = package_session(session_data)
    
    # Step 3: Save
    saved_path = save_session(package, args.output)
    
    # Step 4: Start proxy
    start_proxy(package, args.port)


if __name__ == "__main__":
    main()
