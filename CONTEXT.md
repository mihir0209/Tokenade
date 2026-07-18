# Tokenade - Browser Session Portability

Tokenade extracts, transfers, and injects browser sessions across machines and browsers. The core domain is session portability — making logged-in states moveable.

## Local Witness Environment

All currently working browser sessions to export are in Firefox's default Snap profile:

`/home/ghostrider/snap/firefox/common/.mozilla/firefox/nj40lj6y.default`

Use repo-local commands for pre-release witnesses:

`python3 -m tokenade ...`

Do not use the system-wide installed `tokenade` binary for local end-to-end validation.

## Language

**Session**:
A collection of cookies, tokens, and storage data that proves a user is logged in on a specific site. Stored as a `.tokenade` file (JSON with optional encryption).
_Avoid_: cookie file, token file, auth data

**Session Packager**:
Assembles cookies + fingerprint + tokens + storage into a `.tokenade` file. Handles serialization, encryption, and format normalization.
_Avoid_: exporter, serializer

**Session Loader**:
Injects a `.tokenade` file into a live browser. Handles cookie normalization, Playwright integration, and validation.
_Avoid_: importer, injector

**Site Handler**:
A plugin that knows how to interact with a specific site — extract sessions, validate auth status, handle login flows. Registered by site name (e.g., `"google"`, `"github"`).
_Avoid_: site plugin, site adapter

**OAuth Automation**:
Using a stored OAuth provider session (e.g., Google) to authenticate on a third-party site that offers "Sign in with {Provider}". The plugin automates the browser interactions: clicking the OAuth button, handling the provider's account selector, waiting for redirect, and exporting the resulting session.
_Avoid_: SSO automation, login automation

**CloakBrowser**:
A stealth browser binary with C++ source-level patches that defeat bot detection. Returns standard Playwright objects. Required for sites that actively detect headless browsers (e.g., Google).
_Avoid_: stealth browser, undetectable browser

**Plugin**:
A modular extension that adds site-specific behavior (handlers), session refresh logic, proxy providers, captcha solving, or notification delivery. Plugins declare dependencies on other plugins and are loaded from `~/.tokenade/plugins/`.
_Avoid_: extension, module, addon

**Source Session**:
The `.tokenade` file containing the OAuth provider's cookies (e.g., Google cookies from `google.com`). This is the input to an OAuth automation flow.
_Avoid_: input session, provider session

**Target Session**:
The `.tokenade` file produced after successful OAuth on a third-party site. Contains the site's own session cookies (e.g., `labs.google`'s NextAuth JWT). This is the output of an OAuth automation flow.
_Avoid_: output session, result session

**Stealth Level**:
The degree of browser fingerprint spoofing applied: `"basic"` (JS patches only), `"advanced"` (JS + launch args), `"maximum"` (JS + args + CloakBrowser binary).
_Avoid_: evasion level, anti-detection level
