# Session Compatibility Matrix

Session portability has multiple capability levels. A visible logged-in page is
not evidence that state mutations, outbound operations, calls, or concurrent use
are safe.

## Access Modes

| Mode | Meaning | Active-use behavior |
|------|---------|---------------------|
| `clone` | Concurrent copies are supported by the site's credential model. | Reusable without special acknowledgement. |
| `exclusive_move` | Mutable device state must have one active owner. | Source must be retired; explicit acknowledgement required. |
| `single_use` | Artifact is intended for one local materialization. | Requires a local claim; offline copies cannot be globally prevented. |
| `relink_required` | Supporting state can move, but authentication cannot. | Active authenticated replay is rejected. |

## Capability Levels

| Capability | Required evidence |
|------------|-------------------|
| Authentication | Logged-in UI, no login challenge |
| Inbound sync | New remote state arrives |
| Mutation | Read/archive/star/settings changes persist |
| Outbound | Direct and group sends reach remote devices and own-device copies |
| Calls | Voice/video signaling starts and completes |
| Persistence | Capabilities survive reload and full browser restart |
| Concurrency | Source and target can operate simultaneously without state divergence |

## Current Evidence

| Site/handler | Source | Target | Access mode | Evidence | Status |
|--------------|--------|--------|-------------|----------|--------|
| WhatsApp 1.2.0 | Linux Brave | Linux/Windows Chromium | `exclusive_move` | Auth and inbound sync passed; concurrent clones broke outbound/calls | Experimental, unverified |

WhatsApp's companion-device state includes mutable Signal sessions, Sender Keys,
prekeys, application-state versions, and call signaling. Each concurrent browser
must be linked independently. See the marketplace handler's `VERIFICATION.md`.
