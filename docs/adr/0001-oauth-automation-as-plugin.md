# ADR-0001: OAuth Automation as Plugin, Not Core

Google OAuth automation (clicking sign-in buttons, handling account selectors, exporting target sessions) is implemented as a plugin (`OAuthAutomationPlugin`), not as core infrastructure.

The alternative was adding OAuth automation to core modules (e.g., `core/browser/oauth.py`). This was rejected because: (1) OAuth flows are site-specific — different sites have different button selectors, popup vs redirect behavior, and account chooser UIs; (2) core already has 9+ consumers of `BrowserProfileDiscovery` and session loading — adding site-specific automation there increases coupling; (3) plugins already support `dependencies` for cross-plugin communication (e.g., google-flow depends on google-handler for session validation).

The trade-off is that plugins require an extra discovery/loading step, but this is already handled by `PluginLoader` and the plugin ecosystem is the intended extension point for site-specific behavior.
