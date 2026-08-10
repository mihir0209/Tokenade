"""
Example: Programmatic Plugin Usage

This script demonstrates how to use the Tokenade plugin system
programmatically (without CLI).

Usage:
    python using_plugins.py

Prerequisites:
    pip install tokenade
    tokenade plugin install oauth2
"""

import sys
from pathlib import Path

# Add parent directory to path for development
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def example_basic_loader():
    """Example 1: Basic plugin loading and listing."""
    from tokenade.core.integration.plugin_loader import PluginLoader

    print("=== Example 1: Basic Plugin Loading ===\n")

    loader = PluginLoader()

    # Discover installed plugins
    plugins = loader.discover()
    print(f"Found {len(plugins)} installed plugin(s):")
    for p in plugins:
        print(f"  • {p['name']} v{p.get('version', '?')} ({p.get('type', '?')})")

    # Load all plugins
    loaded_count = loader.load_all()
    print(f"\nLoaded {loaded_count} plugin(s)")

    # List loaded plugins by type
    print(f"\nRefreshers: {list(loader.list_refreshers().keys())}")
    print(f"Handlers: {list(loader.list_handlers().keys())}")
    print(f"Exporters: {list(loader.list_exporters().keys())}")


def example_session_refresh():
    """Example 2: Using a session refresh plugin."""
    from tokenade.core.integration.plugin_loader import PluginLoader

    print("\n=== Example 2: Session Refresh ===\n")

    loader = PluginLoader()
    loader.load_all()

    # Sample session (as if loaded from a .tokenade file)
    sample_session = {
        "version": "2.0",
        "site_name": "google",
        "cookies": [
            {
                "name": "token",
                "value": "old_token_123",
                "domain": ".google.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            }
        ],
        "metadata": {
            "cookie_count": 1,
        },
    }

    # Find a refresher that can handle this session
    refresher = loader.get_refresher_for_session(sample_session)

    if refresher:
        print(f"Found refresher: {refresher.name} v{refresher.version}")

        # In a real scenario, you'd provide actual credentials
        credentials = {
            "client_id": "YOUR_CLIENT_ID",
            "client_secret": "YOUR_CLIENT_SECRET",
            "refresh_token": "YOUR_REFRESH_TOKEN",
        }

        # Uncomment to actually refresh:
        # new_session = refresher.refresh(sample_session, credentials)
        # print(f"Refreshed! New token: {new_session['metadata']['access_token'][:20]}...")
        print("(Refresh skipped — provide real credentials to test)")
    else:
        print("No refresher found for this session")
        print("Install the oauth2 plugin: tokenade plugin install oauth2")


def example_custom_plugin():
    """Example 3: Creating a custom plugin in-memory."""
    from tokenade.plugin import SessionRefreshPlugin

    print("\n=== Example 3: Custom Plugin ===\n")

    class MyCustomPlugin(SessionRefreshPlugin):
        """A custom refresh plugin for demonstration."""

        name = "my-custom"
        version = "0.1.0"
        description = "Custom refresh plugin"

        def can_refresh(self, session):
            return session.get("site_name") == "my-site"

        def refresh(self, session, credentials):
            print(f"  Refreshing session for {session.get('site_name')}...")
            session["metadata"]["refreshed"] = True
            return session

    # Create and use the plugin directly
    plugin = MyCustomPlugin()
    print(f"Plugin: {plugin.name} v{plugin.version}")
    print(f"Description: {plugin.description}")

    # Test can_refresh
    test_session = {"site_name": "my-site", "cookies": []}
    can = plugin.can_refresh(test_session)
    print(f"Can refresh 'my-site': {can}")

    # Test refresh
    if can:
        result = plugin.refresh(test_session, {})
        print(f"Refreshed: {result['metadata']['refreshed']}")


def example_plugin_info():
    """Example 4: Getting plugin information."""
    from tokenade.plugin import SessionRefreshPlugin, SiteHandlerPlugin

    print("\n=== Example 4: Plugin Info ===\n")

    # Show the OAuth2 plugin's info (if installed)
    try:
        from tokenade.plugin.oauth2.plugin import OAuth2Plugin

        plugin = OAuth2Plugin()
        info = plugin.get_info()
        print("OAuth2 Plugin Info:")
        for key, value in info.items():
            print(f"  {key}: {value}")

        print("\nCredentials needed:")
        for arg in plugin.get_credentials_args():
            required = "required" if arg.get("required") else "optional"
            print(f"  {arg['name']} ({required}): {arg['help']}")

    except ImportError:
        print("OAuth2 plugin not installed. Install with:")
        print("  tokenade plugin install oauth2")


def example_plugin_dev_workflow():
    """Example 5: Full plugin development workflow."""
    print("\n=== Example 5: Plugin Development Workflow ===\n")

    print("1. Create plugin directory:")
    print("   mkdir -p ~/.tokenade/plugins/my-plugin")
    print()
    print("2. Create plugin.json:")
    print('   {"name": "my-plugin", "version": "1.0.0", ...}')
    print()
    print("3. Create plugin.py:")
    print("   from tokenade.plugin import SessionRefreshPlugin")
    print("   class MyPlugin(SessionRefreshPlugin): ...")
    print()
    print("4. Test your plugin:")
    print("   tokenade plugin list")
    print("   tokenade plugin info my-plugin")
    print()
    print("5. Publish to registry:")
    print("   - Fork codeberg.org/mihir0209/tokenade-plugins")
    print("   - Add your plugin to plugins.json")
    print("   - Submit a PR")


if __name__ == "__main__":
    print("Tokenade Plugin System — Examples\n")

    example_basic_loader()
    example_session_refresh()
    example_custom_plugin()
    example_plugin_info()
    example_plugin_dev_workflow()

    print("\n" + "=" * 50)
    print("For more examples, see the examples/plugins/ directory")
    print("For documentation, see docs/TUTORIAL_PLUGIN_DEV.md")
