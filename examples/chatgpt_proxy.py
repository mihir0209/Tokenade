#!/usr/bin/env python3
"""
ChatGPT Proxy - Real ChatGPT Session via CDP Proxy

Uses Playwright Chromium with donor cookies and curl-cffi TLS fingerprint matching.
No URL rewriting, no service worker — the browser handles everything natively.
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tokenade.core.proxy.cdp_proxy import CDPProxy, CDPProxyConfig
from tokenade.core.importer.browser_discovery import BrowserProfileDiscovery
from tokenade.core.importer.cookie_extractor import CookieExtractor, SiteFilter


def main():
    # Find browser profiles
    discovery = BrowserProfileDiscovery()
    all_profiles = discovery.discover_all()
    
    print("=== Finding Browser Profiles ===")
    profiles = []
    for browser, profile_list in all_profiles.items():
        for profile in profile_list:
            print(f"  {browser} ({profile.path})")
            profiles.append((browser, profile))
    
    # Extract ChatGPT cookies (under "openai" site)
    site_filter = SiteFilter(sites=["openai"])
    
    cookies = []
    for browser, profile in profiles:
        try:
            extractor = CookieExtractor(profile.path, browser)
            
            if browser == "firefox":
                result = extractor.extract_firefox(site_filter)
            else:
                result = extractor.extract_chrome(site_filter)
            
            if result:
                cookies = result
                print(f"\nFound {len(cookies)} cookies in {browser}")
                break
        except Exception as e:
            print(f"Error with {browser}: {e}")
    
    if not cookies:
        print("\nNo cookies found!")
        print("Please log in to ChatGPT in your browser first.")
        return
    
    print(f"\nLoaded {len(cookies)} cookies")
    for c in cookies[:5]:
        print(f"  - {c['name']} = {c['value'][:30]}...")
    
    # Create session package
    session_package = {
        "version": "2.0",
        "site_name": "chatgpt",
        "site_urls": ["https://chatgpt.com"],
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
    
    # Create CDP proxy
    config = CDPProxyConfig(
        host="127.0.0.1",
        port=9222,
        headless=True,  # Set to False to see the browser window
    )
    
    proxy = CDPProxy(session_package, config)
    
    print("\n" + "="*60)
    print("CHATGPT CDP PROXY SERVER")
    print("="*60)
    print("\nOpen http://127.0.0.1:9222 in your browser")
    print("Enter chatgpt.com in the URL box and press Browse")
    print("\nHow it works:")
    print("  1. Playwright Chromium renders the page")
    print("  2. page.route() intercepts ALL browser requests")
    print("  3. Each request forwarded via curl-cffi (TLS matched)")
    print("  4. Donor cookies injected into browser context")
    print("  5. No URL rewriting needed — browser handles everything")
    print("\nPress Ctrl+C to stop")
    print("="*60 + "\n")
    
    proxy.run()


if __name__ == "__main__":
    main()
