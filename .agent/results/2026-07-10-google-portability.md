# Google session portability — verified results

**Date:** 2026-07-10  
**Artifact used:** `gmail.tokenade` (Firefox donor, Linux)  
**Do not commit** live `.tokenade` session files.

## Verdict

| Claim | Result |
|-------|--------|
| Portable Google cookies work | **YES** (non-Chrome targets) |
| Multi-browser same jar | **YES** (Brave + Vivaldi concurrent) |
| Multi-device same jar | **YES** (Linux → Windows friend: Brave + Edge) |
| Chrome-family target | **FAIL** (clean profile still signed out) |
| Hard “max 2 sessions” limit | **NO** (3+ concurrent non-Chrome OK) |

## Working recipe

### 1. Export (donor must not be Chrome / Google-owned)

```bash
# Explicit domains
tokenade export --browser-name firefox \
  --domains "google.com,accounts.google.com" \
  -o gmail.tokenade

# Or plugin-driven domains (google-handler overrides default worker)
tokenade export --browser-name firefox \
  --plugin google-handler \
  -o gmail.tokenade
```

**Donor browsers:** Firefox, Brave, Edge, Vivaldi  
**Avoid as donor/target:** Google Chrome, Chromium, Chrome Canary/Beta, other Google-owned browsers

### 2. Launch (clean profile always)

```bash
# Linux / macOS (macOS not re-verified this run; expect same flow + path quirks)
tokenade launch --browser brave \
  --session gmail.tokenade \
  --url "https://mail.google.com/mail/u/0/#inbox" \
  --profile-dir /tmp/tokenade-brave-clean \
  --port 9223 --visible

# Plugin sets dashboard URL + filters cookies
tokenade launch --browser brave \
  --session gmail.tokenade \
  --plugin google-handler \
  --profile-dir /tmp/tokenade-brave-clean \
  --port 9223 --visible
```

### Windows (PowerShell) — verified on friend laptop

```powershell
$tokenade = "$env:USERPROFILE\Downloads\gmail.tokenade"

python -m tokenade launch --browser brave --session $tokenade `
  --url "https://mail.google.com/mail/u/0/#inbox" `
  --port 9223 --profile-dir "$env:TEMP\tokenade-brave-friend" --visible

python -m tokenade launch --browser edge --session $tokenade `
  --url "https://mail.google.com/mail/u/0/#inbox" `
  --port 9224 --profile-dir "$env:TEMP\tokenade-edge-friend" --visible
```

### Rules that matter

1. **Clean `--profile-dir`** — never inject into a dirty system Chrome/Brave profile for tests  
2. **Navigate product URL directly** (e.g. `mail.google.com`) — do **not** bounce through `accounts.google.com` after inject  
3. **Avoid Chrome-family** for Google sessions  
4. Multi-device / multi-browser reuse of the **same jar is OK** on non-Chrome  
5. macOS: not tested this run; expect identical CLI, different browser paths only  

## Test matrix (this campaign)

| # | Path | Result |
|---|------|--------|
| 1 | FF export → Brave clean (Linux) | Inbox (3,703) mihirpatil128 |
| 2 | Same jar → Vivaldi clean (Linux, concurrent) | Inbox (same) |
| 3 | Same jar → Windows Brave + Edge (friend) | Both loaded session |
| 4 | Same jar → Chrome clean (Linux, canary binary via google-chrome) | **accountchooser / signed out** |
| 5 | Plugin export `google-handler` → Brave launch `--plugin google-handler` | Inbox |

### Chrome kill-test detail

- Profile: `/tmp/tokenade-chrome-killtest-*` (fresh)  
- Injected: 180/180 cookies  
- Final URL: `accounts.google.com/v3/signin/accountchooser?...`  
- Title: `Gmail` (not Inbox)  
- Confirms: Chrome-family rejection is real, not “dirty profile” or “third session”

## Prior false negatives (superseded)

Earlier battle report (`.agent/testing-reports/2026-07-09-google-portability-battle.md`) failed due to stale/signed-out cookies, dirty profiles, and accounts.google bounce — **not** because Google forbids all portability.

## CLI messaging

Launch tips now say: prefer non-Chrome; multi-device OK; avoid inventing “one device only / DBSC always kills”.
