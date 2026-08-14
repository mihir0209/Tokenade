# ADR-0004: Plugin Publication Gated on Config Validation

Plugins are published to the event bus, registered in the shared context, and wired into typed registries only after `on_configure` validates the provided config. A plugin that fails validation is reported as `FAILED` (with a `PLUGIN_ERROR` event) and is never registered; a plugin that passes validation but declares `configuration_valid = False` stays `LOADED` and unregistered until it is configured. Direct consumers (proxy provider resolver, artifact manager, browser feature gating) treat anything other than `PluginState.ACTIVE` as unavailable.

The alternatives were rejected for these reasons:

- Publishing before validation meant other plugins and consumers could observe a half-configured plugin, emit `PLUGIN_LOADED` for a plugin that immediately fails, and let direct consumers use a plugin whose `on_configure` never succeeded. The review (CR-05/CR-10) found exactly this: `load_plugin` published the loaded event and registered the plugin before the config step could veto it.
- Letting each consumer interpret `LOADED`/`FAILED`/`CONFIGURED` differently caused divergent behavior: the proxy provider silently used a plugin that was never configured, while the CLI's requirement gate treated `CONFIGURED` as usable. A single rule — only `ACTIVE` is usable — keeps every consumer consistent.

The trade-offs are that an unconfigured-but-valid plugin requires an explicit configure step before any consumer can use it (e.g., `webhook-notify` shows `[loaded]` until configured), and that plugins which used to work while unconfigured now fail closed with a clear `not active (state: ...)` error instead of failing later at use time.
