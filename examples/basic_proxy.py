#!/usr/bin/env python3
"""
Basic Proxy - Any Site Session Proxy
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.core.proxy.server import TokenadeProxy, ProxyConfig
from tokenade.core.importer.browser_discovery import BrowserDiscovery
from tokenade.core.importer.cookie_extractor import CookieExtractor


def main():
    # Find and extract real cookies from browser
    discovery = BrowserDiscovery()
    profiles = discovery.find_browser_profiles()
    
    print("=== Finding Browser Profiles ===")
    for profile in profiles:
        print(f"  {profile['browser']} ({profile['path']})")
    
    # Extract cookies for any site
    extractor = CookieExtractor()
    site_config = {
        "id": "any",
        "name": "Any Site",
        "urls": [{"pattern": ".", "type": "domain"}]
    }
    
    cookies = []
    for profile in profiles:
        try:
            result = extractor.extract_cookies(profile, site_config)
            if result.get("cookies"):
                cookies = result["cookies"]
                print(f"\nFound {len(cookies)} cookies in {profile['browser']}")
                break
        except Exception as e:
            print(f"Error: {e}")
    
    if not cookies:
        print("\nNo cookies found!")
        return
    
    print(f"\nLoaded {len(cookies)} cookies")
    for c in cookies[:5]:
        print(f"  - {c['name']} = {c['value'][:30]}...")
    
    # Create session package
    session_package = {
        "version": "2.0",
        "site_name": "any",
        "site_urls": [],
        "cookies": cookies,
        "fingerprint": {
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "http_version": "2",
            "cipher_suites": [
                "TLS_AES_128_GCM_SHA256",
                "TLS_AES_256_GCM_SHA384",
                "TLS_CHACHA20_POLY1305_SHA256",
                "ECDHE-ECDSA-AES128-GCM-SHA256",
                "ECDHE-RSA-AES128-GCM-SHA256",
                "ECDHE-ECDSA-AES256-GCM-SHA384",
                "ECDHE-RSA-AES256-GCM-SHA384"
            ],
            "signature_algorithms": [
                "ecdsa_secp256r1_sha256",
                "rsa_pss_rsae_sha256",
                "rsa_pkcs1_sha256"
            ],
            "extensions": ["http/1.1", "h2", "h2c"]
        },
        "tls_profile": {
            "browser": "chrome",
            "version": "120",
            "impersonate": "chrome120",
            "http_version": "2"
        }
    }
    
    # Create proxy
    config = ProxyConfig(
        host="127.0.0.1",
        port=9222,
        gui_mode=True
    )
    
    proxy = TokenadeProxy(session_package, config)
    
    print("\n" + "="*60)
    print("PROXY SERVER")
    print("="*60)
    print("\nOpen http://127.0.0.1:9222 in your browser")
    print("Type any URL and press Enter")
    print("\nPress Ctrl+C to stop")
    print("="*60 + "\n")
    
    proxy.run()


if __name__ == "__main__":
    main()
