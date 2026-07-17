# Gateway And Request Framework Plan

**Date:** 2026-07-18  
**Status:** Approved direction, pending implementation  
**North star:** Tokenade should port sessions through isolated, consistent browser identities while exposing a programmable request framework for plugins, routing, gateway control, and future upstream proxy providers.

## Why This Plan Exists

The current CLI has two proxy-shaped concepts mixed together:

- **Gateway:** Tokenade-specific local control plane for serving and rotating multiple `.tokenade` sessions.
- **Proxy:** Universal upstream network proxy concept: residential, sticky, rotating, provider-backed egress.

These concepts are both valuable but should not share one overloaded command. The project will use `gateway` for Tokenade's unique local session-routing control plane and reserve `proxy` for upstream network proxy work.

## Decisions

| Topic | Decision |
|---|---|
| Local multi-session control plane name | `gateway` |
| Upstream network proxy name | `proxy` |
| Gateway rotation object | `session` |
| Gateway runtime model | Multiple isolated session contexts; rotate active context for future work |
| In-place cookie/storage swap | Not default; unsafe for high-value sites |
| Existing tabs during rotation | Drain old tabs; new work uses newly active session |
| Minimum timed rotation interval | Hardcoded `5s` floor |
| Switch processing target | Under hundreds of milliseconds |
| `request.json` | Unified nested request framework, not always flat |
| Plugin entries | Ordered array |
| Plugin roles | Dict keyed by known role names; role values are role-specific config objects |
| Plugin config | Dynamic pass-through object; plugin decides what to use or ignore |
| Missing required plugins | Fail closed with install suggestions |
| Registry-specific missing plugin lookup | Do not do registry source inference in first pass |
| Source network stamp | Explicit opt-in, or via explicit proxy-provider metadata flow |
| Raw source IP storage | Never by default; only with explicit flag |
| Gateway visibility | Hidden until end-to-end gateway serving and witness tests exist |

## Market Reality Check

Recent anti-detect and multi-account product docs consistently model an account as an isolated browser profile, not as a mutable cookie jar.

Current product guidance from GoLogin, Multilogin, and Octo Browser emphasizes:

- each browser profile has its own fingerprint, cookies, storage, cache, extensions, and proxy;
- existing accounts require stable profiles and stable proxy/location;
- mobile/residential sticky proxies are useful because they keep IP and location consistent;
- frequent IP/country/region changes can trigger checks;
- cookie import can overwrite data and must be used carefully.

That supports the D-model for gateway rotation:

```text
Multiple isolated browser contexts, one per active session. Rotation changes the active context for future work. Existing tabs drain.
```

It rejects the A-model as the default:

```text
Replace cookies/storage in a single live browser context.
```

The A-model may later exist as an explicit unsafe/fast mode for simple cookie-only sites, but it should not define the gateway.

## Target Command Vocabulary

```text
gateway = many sessions, local control plane, routing, scheduling hooks, API control
launch = one session, open in browser
proxy = upstream network egress: residential/sticky/rotating provider integration
run = execute plugin operations from request.json
```

`gateway` should supersede the old overloaded local proxy meaning. `proxy` should later become the upstream proxy tool.

## Request JSON Direction

`request.json` becomes a nested operation envelope.

The core validates common structure only:

- `version`
- `operation`
- `plugins[]`
- `plugins[].name`
- `plugins[].required`
- `plugins[].roles`
- known routing/session/gateway fields when relevant to the operation

The core passes plugin `config` and role-specific data through unchanged. This preserves flexibility for large provider or Site Handler plugins that need richer config than flat args.

### Plugin Object Shape

```json
{
  "name": "brightdata",
  "required": true,
  "roles": {
    "proxy_provider": {
      "mode": "sticky",
      "nearest_to_source": true,
      "match_source_location": true,
      "fallback": "fail"
    }
  },
  "config": {
    "zone": "residential",
    "country": "auto",
    "city": "auto"
  }
}
```

### Run Operation Shape

```json
{
  "version": "1",
  "operation": "run",
  "plugins": [
    {
      "name": "generic-handler",
      "required": true,
      "roles": {
        "run": {
          "method": "process"
        }
      },
      "config": {
        "session_file": "/tmp/real-sessions/github.tokenade",
        "site": "github"
      }
    }
  ],
  "execution": {
    "stop_on_error": true
  }
}
```

### Gateway Operation Shape

```json
{
  "version": "1",
  "operation": "gateway",
  "sessions": {
    "dir": "./sessions",
    "pattern": "*.tokenade"
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 9222,
    "backend": "cdp"
  },
  "routing": {
    "object": "session",
    "strategy": "health-weighted",
    "switch_interval_seconds": 30,
    "sticky_by": "site",
    "failover": true,
    "drain_existing_tabs": true
  },
  "plugins": [
    {
      "name": "discord-handler",
      "required": true,
      "roles": {
        "site_handler": {
          "sites": ["discord"]
        }
      },
      "config": {}
    },
    {
      "name": "brightdata",
      "required": true,
      "roles": {
        "proxy_provider": {
          "mode": "sticky",
          "nearest_to_source": true,
          "match_source_location": true,
          "fallback": "fail"
        }
      },
      "config": {
        "zone": "residential"
      }
    }
  ],
  "schedule": {
    "enabled": false
  }
}
```

## Missing Plugin UX

When a required plugin is missing:

```text
Required plugin not installed: alphaM

Try:
  tokenade plugin install alphaM
  tokenade plugin install alphaM --registry <registry-name-or-url>
```

Do not infer exact registry source in the first pass.

## Source Network Stamp

Source network stamping is opt-in and approximate by default.

Allowed triggers:

- explicit `--stamp-network`;
- export request/config that explicitly mentions a proxy provider and source matching metadata flow.

`--proxy-plugin` during export means metadata/provider capability only. It must not route export traffic through that proxy unless a separate explicit future flag says so.

Default stamp shape:

```json
{
  "source_network": {
    "captured_at": "2026-07-18T...",
    "provider": "tokenade-default-ip-lookup",
    "approx_country": "US",
    "approx_region": "CA",
    "approx_city": "San Francisco",
    "timezone": "America/Los_Angeles",
    "asn": "AS...",
    "asn_type": "residential",
    "raw_ip_stored": false
  }
}
```

Raw source IP is only stored with explicit opt-in.

## Phase Order

1. **Request Framework + Nested Run**
   - Build request loader/validator.
   - Replace `tokenade run` with nested `--request` execution.
   - Support ordered multi-plugin execution.

2. **SessionRouter Core**
   - Add session records and selection strategies.
   - Enforce switch interval floor.
   - Benchmark selection against real sessions.

3. **Hidden Gateway API Skeleton**
   - Add hidden `gateway --request request.json`.
   - Validate request/plugins/sessions/routing.
   - Start API endpoints: `/status`, `/sessions`, `/route/next`, `/route/select`.

4. **Gateway Runtime Integration**
   - Wire gateway routing into isolated browser contexts.
   - One context per session.
   - Existing tabs drain; new work uses active context.

5. **Source Network Stamp + Proxy Provider Resolver**
   - Add explicit source network stamp capture.
   - Normalize proxy provider plugin outputs.
   - Preserve privacy and do not print secrets by default.

6. **Promotion + Witness**
   - Only make `gateway` visible when it works end-to-end with witness tests.
   - Reassign `proxy` command to upstream proxy tooling after provider resolver is real.

## Non-Goals For First Slice

- No full CDP context switching in the first request framework slice.
- No visible `gateway` command until end-to-end serving exists.
- No default raw IP collection.
- No in-place live tab cookie/storage mutation as default gateway behavior.
- No registry source inference for missing plugins.

## Open Implementation Questions

- Whether old flat `tokenade run <plugin> --input` should be removed immediately or kept as hidden compatibility during the transition.
- Whether the gateway control API should use `aiohttp` directly or reuse existing proxy server utilities.
- Whether `SessionRouter` should score health from the existing `SessionHealthChecker` on every route decision or consume precomputed health snapshots.
- Whether request validation should warn or reject unknown top-level fields. Current direction: allow unknown fields unless they conflict with known operation fields.
