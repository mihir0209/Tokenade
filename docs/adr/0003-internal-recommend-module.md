# ADR-0003: Internal `recommend` Module — Site/Plugin/Browser Selection

## Context

The CLI/SDK/daemon each need to answer three connected questions for any given
session, URL, or cookie list:

1. Which **site** is this? (e.g. `google`, `chatgpt`, `discord`)
2. Which **plugin** should handle it? (e.g. `generic-handler`, `google-flow-handler`)
3. Which **browser binary** should launch it? (e.g. `cloak`, `firefox`, `brave`)

Today this logic is scattered across at least five call sites, with three
overlapping hardcoded site catalogs (`SITE_DETECTION` 7 sites,
`SITE_URLS` 17 sites, `DETECTION_SITES` for battle testing) plus an alias map
(`_ALIASES`) that lives only in `handlers/resolve.py`. Two recommend-*functions*
-in-disguise already exist — `SiteFilter.detect_site` (cookies→site) and
`PluginExporter.find_handler` (domains→plugin) — but neither calls the other.
A `preferred_plugin` field exists in normalized site_configs but is never
consulted by any resolver. There is no canonical site→plugin→browser answer.

We need a `recommend` capability to (a) make this single decision a first-class
operation (b) drive the new `tokenade recommend` CLI command and (c) let the
planner-with-docs / grill sessions discuss one place.

## Decision

Add a single **internal core module** `tokenade/core/recommend/` (NOT a
marketplace plugin — recommending plugins would make it self-referential).
It exposes three pure functions that compose, plus one
"give me everything" entrypoint:

```python
# tokenade/core/recommend/__init__.py  (re-exported from tokenade top-level)
Recommendation            # dataclass: site, plugin, browser, confidence, reasons[]

recommend_site(*, cookies=None, url=None, domains=None) -> Optional[str]
recommend_plugin(*, site=None, url=None, session=None, cookies=None) -> Optional[str]
recommend_browser(*, site=None, plugin=None, session=None) -> str
recommend(*, session=None, url=None, domains=None, cookies=None) -> Recommendation
```

### Data sources (consulted, not duplicated)

- `tokenade.core.importer.cookie_extractor.SITE_DETECTION` — site → domains/critical cookies
- `tokenade.core.importer.site_configs.{list_site_configs, get_site_config}` — runtime catalog + `preferred_plugin`
- `tokenade.handlers.resolve._ALIASES` — alias normalization (`gh`→`github` etc.)
- `tokenade.core.integration.plugin_loader.PluginLoader.list_handlers` — installed handler plugins
- `tokenade.core.config.DEFAULTS["automation_browser"]` — `"cloak"` default
- `plugin.json` manifest `browser.default` / `browser.allowed` — per-plugin browser preference

### Resolution order

**`recommend_site`** (cookies → site_name):
1. If `session` has `metadata.site_name`, return it (already specified upstream).
2. Delegate to `SiteFilter.detect_site(cookies)` — domain match, then critical cookie names.
3. Try URL host against `SITE_DETECTION` domains.
4. Fall back to the longest unique cookie-domain suffix (e.g. `chatgpt.com`), cross-checked against installed site_configs.
5. `None` if nothing stuck.

**`recommend_plugin`** (site/url/session/cookies → plugin name):
1. If `site` is set, check `get_site_config(site).preferred_plugin`.
2. If a plugin manifest declares this site in its `sites/*.json` catalog (e.g. `generic-handler`), prefer it.
3. Use `PluginExporter.find_handler(domains)` (existing logic — specific beats generic).
4. If nothing found but `generic-handler` installed, return `generic-handler` as catch-all with low confidence.
5. `None` if no installed handler applies.

**`recommend_browser`** (site/plugin/session → browser binary):
1. If `session.metadata.automation_browser` set, return it (user override).
2. If plugin manifest has `browser.default`, return it.
3. Hardcoded per-site rules (Google → `"cloak"` because Chrome is detected; Discord → `"cloak"` for similar reasons).
4. Fall back to `config.DEFAULTS["automation_browser"]` (`"cloak"`).

**`recommend`** (everything) — orchestrates all three, returns a `Recommendation` with `site`, `plugin`, `browser`, `confidence` (0.0–1.0), and `reasons` (list of strings explaining each choice). This is what the CLI and external callers use.

### Configurability

- `RecommendationConfig` dataclass passes through optional `plugins_dir`, `site_configs_dir`, `automation_browser_override`. Defaults read from `~/.tokenade`.
- No new config file. No new environment variables. The CLI is the front door.

### CLI command

```
tokenade recommend --session <path>          # full Recommendation
tokenade recommend --url https://chatgpt.com # site + browser from URL only
tokenade recommend --domains google.com ...  # site + handler from domains
tokenade recommend --json                    # machine-readable
```

Output (human form):
```
site:     chatgpt   (confidence 0.92)
plugin:   generic-handler   (site_config.preferred_plugin)
browser:  cloak     (config.automation_browser)
reasons:
  - cookies matched 5 domains on chatgpt.com
  - generic-handler site_config.chatgpt.json lists chatgpt.com
  - plugin manifest declares browser.default = cloak
  - no per-site browser override
```

### Non-goals

- Not a marketplace plugin (would be self-referential).
- Does not install, download, or execute plugins — pure query.
- Does not replace `find_handler` / `resolve_legacy_handler_class` immediately. It composes over them and provides a unified answer; refactoring those callers to call `recommend` instead is a follow-up (smaller, mechanical).
- Does not consolidate `SITE_URLS` / `DETECTION_SITES` into one catalog yet — only consults `SITE_DETECTION`. Consolidation is a separate ADR (the catalogs are used for different purposes today).
- No ML, no scoring beyond confidence buckets (`high`/`medium`/`low`).

## Status

Proposed.
