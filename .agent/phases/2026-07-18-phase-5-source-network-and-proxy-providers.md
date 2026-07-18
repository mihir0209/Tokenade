# Phase 5: Source Network Stamp And Proxy Providers

**Date:** 2026-07-18  
**Status:** Complete  
**Parent plan:** `.agent/plans/2026-07-18-gateway-request-framework.md`

## Progress

- 2026-07-18: Started implementation.
- 2026-07-18: Confirmed export path has no source network stamping yet and no `--proxy-plugin` semantics; Phase 5 will add explicit opt-in metadata only and will not route export traffic through a proxy.
- 2026-07-18: Added `tokenade.core.network.source_context` with explicit source-network lookup and default raw-IP omission.
- 2026-07-18: Added export flags: `--stamp-network`, `--include-source-ip`, and `--proxy-plugin`; proxy plugin flag records metadata only and does not route export traffic.
- 2026-07-18: Added `tokenade.core.proxy.provider` with provider plugin resolution, normalized proxy shape, and redacted output by default.
- 2026-07-18: Gateway request `plugins[].roles.proxy_provider` now resolves upstream proxy metadata, passes source network metadata when present, redacts credentials in status output, and fails closed for missing required providers.
- 2026-07-18: Added focused tests for source-network privacy, proxy provider resolution/redaction, export parser flags, and gateway provider status metadata.
- 2026-07-18: Verified focused and broader regression slices pass; witnessed source metadata and redacted proxy output with fake lookup/provider.

## Verification

```bash
python3 -m pytest tokenade/tests/test_source_network_context.py tokenade/tests/test_proxy_provider_resolver.py tokenade/tests/test_cli_gateway.py tokenade/tests/test_gateway_server.py -q
python3 -m pytest tokenade/tests/test_source_network_context.py tokenade/tests/test_proxy_provider_resolver.py tokenade/tests/test_cli_gateway.py tokenade/tests/test_gateway_server.py tokenade/tests/test_gateway_runtime.py tokenade/tests/test_gateway_session_router.py tokenade/tests/test_request_config.py tokenade/tests/test_plugin_run_cli.py tokenade/tests/test_cli.py -q
python3 -m flake8 tokenade/core/network tokenade/core/proxy/provider.py tokenade/core/gateway/server.py tokenade/cli/session_export.py tokenade/tests/test_source_network_context.py tokenade/tests/test_proxy_provider_resolver.py tokenade/tests/test_cli_gateway.py tokenade/tests/test_gateway_server.py --max-line-length=120 --ignore=E501,W503,W293,E203,F541,F841,E306,E402,E226,E128,E127,E731,F821,F401,F811,E401,E704
```

Witness result:

```json
{
  "provider_received_country": "US",
  "proxy_redacted": {
    "metadata": {
      "country": "US"
    },
    "mode": "sticky",
    "password": "***",
    "provider": "brightdata",
    "server": "http://proxy.example:8080",
    "username": "us***"
  },
  "secret_in_redacted": false,
  "stamp_country": "US",
  "stamp_has_ip": false,
  "stamp_raw_ip_stored": false
}
```

## Goal

Add privacy-conscious source network stamping and provider-backed upstream proxy resolution through proxy provider plugins.

## Scope

- Add source network metadata capture on explicit opt-in.
- Normalize proxy provider plugin results.
- Support sticky/residential matching using source network metadata.
- Avoid printing or storing secrets unnecessarily.

## Privacy Rules

- No network/IP lookup unless explicitly opted in.
- Raw source IP is not stored by default.
- Raw source IP requires explicit flag, e.g. `--include-source-ip`.
- Approximate location is acceptable by default.
- Export traffic is not routed through `--proxy-plugin` unless a separate future explicit flag exists.

## Source Stamp Shape

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

## Request JSON Proxy Provider Role

Proxy providers are plugins, not a dedicated top-level proxy section.

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
    "zone": "residential"
  }
}
```

## Provider Resolver Responsibilities

- Load required proxy provider plugin.
- Pass role config, plugin config, session metadata, and source network metadata to plugin.
- Normalize returned proxy into a common internal shape.
- Redact credentials in logs/API responses by default.
- Provide explicit `show_secrets` behavior only where required.

## Candidate Files

- `tokenade/core/network/source_context.py`
- `tokenade/core/proxy/provider.py`
- `tokenade/core/importer/session_packager.py`
- `tokenade/cli/session_export.py`
- `tokenade/plugin/base.py`
- `tokenade/tests/test_source_network_context.py`
- `tokenade/tests/test_proxy_provider_resolver.py`

## Tests

- No source lookup without explicit opt-in.
- Stamp includes approximate location fields.
- Raw IP omitted by default.
- Raw IP included only with explicit flag.
- Proxy provider plugin receives source network metadata when matching is requested.
- Proxy credentials are redacted in output by default.
- Missing required provider plugin fails closed.

## Witness

- Export a real session with `--stamp-network` and verify metadata shape.
- Use a fake/test proxy provider plugin to resolve sticky proxy nearest to source metadata.
- Verify logs/API do not expose credentials.

## Exit Criteria

- Source network metadata is captured only with consent.
- Proxy provider integration can choose sticky/residential egress based on source metadata.
- Secrets are redacted by default.
