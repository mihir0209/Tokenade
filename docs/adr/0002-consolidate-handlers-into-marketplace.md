# ADR-0002: Consolidate Handlers into Marketplace, Keep Base Classes in Core

Core contains full implementations of Google, GitHub, GenericOAuth handlers and an OAuth2 plugin — all duplicated in the `tokenade-plugins` marketplace. This creates confusion, maintenance burden, and tight coupling.

The decision is to: (1) move valuable functionality (login automation, token extraction, API testing) from core handlers into marketplace plugins, (2) decouple `resolve.py` from concrete handlers so CLI commands use the plugin system, (3) remove duplicate implementations from core, (4) keep only base classes (`SiteHandler`, `HandlerRegistry`, `PluginBase`, `SiteHandlerPlugin`) in core.

The alternative — keeping both systems — was rejected because the `__init__.py` already documents the legacy system as deprecated and the marketplace as the preferred path. Maintaining both doubles the surface area for bugs and confuses contributors about which system to use.

The trade-off is that marketplace plugins must absorb the functionality currently in core handlers (login automation, token extraction) before the core copies can be removed. This is done in phases: enrich marketplace first, then remove from core.
