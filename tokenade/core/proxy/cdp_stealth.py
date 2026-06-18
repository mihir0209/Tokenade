"""
CDP Proxy — Stealth script, URL safety, and blocked networks.
"""

import ipaddress
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def is_safe_url(url: str) -> bool:
    """Check if a URL is safe to proxy (not targeting internal networks)."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname in ("localhost", "0.0.0.0", "[::]", "metadata.google.internal"):
            return False
        try:
            addr = ipaddress.ip_address(hostname)
            for net in BLOCKED_NETWORKS:
                if addr in net:
                    return False
        except ValueError:
            pass
        return True
    except (ValueError, TypeError) as e:
        logger.debug("URL safety check failed: %s", e)
        return False


COMPREHENSIVE_STEALTH_SCRIPT = """
(function() {
    'use strict';

    // ===== 1. Remove navigator.webdriver =====
    Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // ===== 2. Add window.chrome =====
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: function() {},
            sendMessage: function() {},
            onMessage: { addListener: function() {}, removeListener: function() {} },
            onConnect: { addListener: function() {}, removeListener: function() {} }
        };
    }

    // ===== 3. Fix navigator.plugins =====
    const pluginData = [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
    ];

    const pluginArray = Object.create(PluginArray.prototype);
    pluginData.forEach((p, i) => {
        const plugin = Object.create(Plugin.prototype);
        Object.defineProperties(plugin, {
            name: { get: () => p.name, configurable: true },
            filename: { get: () => p.filename, configurable: true },
            description: { get: () => p.description, configurable: true },
            length: { get: () => 0, configurable: true }
        });
        pluginArray[i] = plugin;
    });
    Object.defineProperty(pluginArray, 'length', { get: () => pluginData.length, configurable: true });
    pluginArray.item = function(i) { return this[i] || null; };
    pluginArray.namedItem = function(n) { return pluginData.find(p => p.name === n) ? this[pluginData.findIndex(p => p.name === n)] : null; };
    pluginArray.refresh = function() {};

    Object.defineProperty(navigator, 'plugins', { get: () => pluginArray, configurable: true });

    // ===== 4. Fix navigator.languages =====
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true
    });
    Object.defineProperty(navigator, 'language', {
        get: () => 'en-US',
        configurable: true
    });

    // ===== 5. Fix navigator.permissions.query =====
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (params) => {
        if (params.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission });
        }
        return origQuery(params);
    };

    // ===== 6. Remove headless indicators =====
    if (window.outerWidth === 0) {
        Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth, configurable: true });
    }
    if (window.outerHeight === 0) {
        Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 85, configurable: true });
    }

    // ===== 7. WebGL fingerprint consistency =====
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Google Inc. (Intel)';
        if (param === 37446) return 'ANGLE (Intel, Mesa Intel(R) UHD Graphics 630, OpenGL 4.6)';
        return getParameter.call(this, param);
    };

    // ===== 8. Remove DevTools protocol indicators =====
    const origGetter = Object.getOwnPropertyDescriptor(Navigator.prototype, 'userAgent');
    if (origGetter && origGetter.get) {
        const ua = origGetter.get.call(navigator);
        if (ua.includes('HeadlessChrome')) {
            Object.defineProperty(navigator, 'userAgent', {
                get: () => ua.replace('HeadlessChrome', 'Chrome'),
                configurable: true
            });
        }
    }

    // ===== 9. Console.debug override =====
    const origDebug = console.debug;
    console.debug = function() { return origDebug.apply(this, arguments); };

    // ===== 10. Fix screen dimensions for headless =====
    if (screen.width === 0 || screen.height === 0) {
        Object.defineProperty(screen, 'width', { get: () => 1920, configurable: true });
        Object.defineProperty(screen, 'height', { get: () => 1080, configurable: true });
        Object.defineProperty(screen, 'availWidth', { get: () => 1920, configurable: true });
        Object.defineProperty(screen, 'availHeight', { get: () => 1040, configurable: true });
        Object.defineProperty(screen, 'colorDepth', { get: () => 24, configurable: true });
        Object.defineProperty(screen, 'pixelDepth', { get: () => 24, configurable: true });
    }

    // ===== 11. navigator.connection =====
    if (!navigator.connection) {
        Object.defineProperty(navigator, 'connection', {
            get: () => ({
                effectiveType: '4g',
                rtt: 50,
                downlink: 10,
                saveData: false
            }),
            configurable: true
        });
    }

    // ===== 12. Remove automation-related properties =====
    const cdcProps = Object.getOwnPropertyNames(window).filter(p => p.startsWith('cdc_'));
    cdcProps.forEach(p => { try { delete window[p]; } catch(e) {} });

    // ===== 13. Override toString to hide patches =====
    const nativeToString = Function.prototype.toString;
    Function.prototype.toString = function() {
        if (this === navigator.permissions.query) {
            return 'function query() { [native code] }';
        }
        if (this === navigator.plugins.item) {
            return 'function item() { [native code] }';
        }
        return nativeToString.call(this);
    };
})();
"""


SITE_URLS = {
    "google": "https://mail.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "discord": "https://discord.com/channels/@me",
    "reddit": "https://www.reddit.com",
    "openai": "https://chatgpt.com",
    "chatgpt": "https://chatgpt.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "linkedin": "https://www.linkedin.com/feed/",
    "netflix": "https://www.netflix.com/browse",
    "youtube": "https://www.youtube.com",
    "amazon": "https://www.amazon.com",
    "spotify": "https://open.spotify.com",
    "microsoft": "https://www.microsoft.com",
}


def get_site_url(session: dict) -> str:
    """Get the default URL for a session's site."""
    from tokenade.core.importer.site_configs import get_site_config

    site_name = session.get("site_name", "unknown")
    if site_name and site_name != "unknown":
        config = get_site_config(site_name)
        if config and config.get("validate_url"):
            return config["validate_url"]

        if site_name.lower() in SITE_URLS:
            return SITE_URLS[site_name.lower()]

        cookies = session.get("cookies", [])
        domains = set()
        for c in cookies:
            d = c.get("domain", "")
            if d:
                domains.add(d.lstrip("."))
        for d in sorted(domains, key=len):
            if site_name.lower() in d.lower():
                return f"https://{d}"
        if domains:
            return f"https://{min(domains, key=len)}"
        return f"https://www.{site_name}.com"
    return "https://example.com"
