# Google Portability Battle Test

**Date:** 2026-07-09  
**Host:** Linux, Brave (running, donor) + headless Brave/Playwright (targets)  
**Session artifact:** `/tmp/tokenade-google-battle/google-brave.tokenade`

## Goal

Prove (or disprove) end-to-end **Google session portability**: export cookies from Brave → inject elsewhere → still logged into Google properties.

## Setup

| Item | Value |
|------|--------|
| Donor | Brave Default `~/.config/BraveSoftware/Brave-Browser/Default` (browser was open) |
| Export | `tokenade export --browser-name brave --domains "google.com,accounts.google.com,mail.google.com"` |
| Decrypt | Fixed Linux OSCrypt (CBC + KWallet Brave Safe Storage) |
| Targets | (A) `tokenade launch -b brave` temp profile headless; (B) Playwright Chromium + cookies; (C) CDP proxy |

## Results

### 1. Export — **PASS**

| Metric | Value |
|--------|------:|
| Cookies | 80 |
| Critical present | SID, SSID, HSID, APISID, SAPISID, LSID, `__Secure-1PSID`, `__Secure-3PSID`, `*PSIDTS` — **all** |
| Values with control chars | **0** |
| Auth metadata | `logged_in` |
| Health score | 97.5% (2 expired non-blocking cookies) |

Decrypt path is healthy. Export is not the blocker.

### 2. Cookie inject — **PASS**

| Path | Injected | Critical cookies in jar after inject |
|------|----------|--------------------------------------|
| Launch Brave temp profile | **80/80** | SID family present |
| Playwright `context.add_cookies` | **80** | present |
| CDP proxy context fallback | **80** (raw CDP batch failed first) | session reports 80 cookies |

Tokenade **can place** decrypted Google cookies into a browser context.

### 3. Google accepts session as logged-in — **FAIL**

| URL | Final URL | Verdict |
|-----|-----------|---------|
| `myaccount.google.com` | `google.com/account/about/?hl=en-US` | Marketing / not authenticated My Account |
| `mail.google.com` | `accounts.google.com/.../accountchooser` | **Choose an account — “Signed out”** for listed identities |
| `accounts.google.com` | account chooser | Same — emails shown, **Signed out** |

Playwright body snip (Gmail chooser):

```
Choose an account
Mihir Patil
mihirpatil128@gmail.com
Signed out
Ritas Deva
ritasdeva81@gmail.com
Signed out
```

So Google **recognizes identities** (some cookies work) but **rejects the auth session** (SID/PSID family not accepted as live login).

### 4. CDP proxy — **PARTIAL (infra OK, auth not proven)**

- Proxy starts; GUI `/` 200; `/status` shows site=google, cookies≈77–80
- Auto-navigate configured to myaccount
- No reliable HTML snapshot of logged-in Gmail from automated probes in this run
- Same underlying Playwright cookie model as (3) → expect same “Signed out” outcome

## Interpretation (honest)

| Layer | Status |
|-------|--------|
| Brave cookie **decrypt** | Works |
| Session **package** | Works |
| **Inject** into Brave/Chromium | Works |
| Google **server-side session trust** | Does **not** accept portable cookie jar in this run |

Likely factors (not mutually exclusive):

1. **Multi-device / concurrent session** — donor Brave was still open and logged in while target used the same cookie set  
2. **Risk signals** — new UA/profile/IP/fingerprint vs donor (headless Chromium/Brave temp profile)  
3. **DBSC / bound session** — Google increasingly binds sessions; non-Chrome still not immune to server checks  
4. **Missing non-cookie state** — some Google flows need storage / device tokens beyond Cookies SQLite  

This matches earlier project notes: **Google is the hard case**; GitHub portability was proven on this machine.

## What worked in the same era (for contrast)

- **GitHub** Firefox → Chrome launch inject: logged in (`current_user=mihir0209`) — prior report  
- **Google** export/decrypt/inject pipeline: mechanically correct, auth rejected  

## Recommended manual follow-ups (with you)

Do these **one at a time** and note yes/no logged-in:

1. **Close donor Brave completely** (all windows), wait ~30s, re-export, inject into temp Brave **headed** (`tokenade launch -b brave -s ... -u https://mail.google.com --visible`).  
2. **Proxy-only multi-device** (cookies never leave machine):  
   `tokenade proxy -s google-brave.tokenade --host 0.0.0.0 --port 9222`  
   Open GUI from another device; do **not** copy the `.tokenade` file.  
3. **Same-browser refresh path**:  
   `tokenade refresh-browser -s google-brave.tokenade -b brave -u https://mail.google.com`  
   (re-warm cookies in a real browser, write updated file)  
4. **Avoid Chrome as Google target** on Windows DBSC; keep Brave/Edge/Firefox as targets.

## Commands used

```bash
tokenade export --browser-name brave \
  --domains "google.com,accounts.google.com,mail.google.com" \
  -o /tmp/tokenade-google-battle/google-brave.tokenade

tokenade health -s /tmp/tokenade-google-battle/google-brave.tokenade

tokenade launch -b brave \
  -s /tmp/tokenade-google-battle/google-brave.tokenade \
  -u https://myaccount.google.com --headless --no-cloak \
  --port 9444 --profile-dir /tmp/tokenade-google-battle/profiles/brave-inject

tokenade proxy -s /tmp/tokenade-google-battle/google-brave.tokenade \
  --port 9455 --no-open-browser --target-url https://myaccount.google.com --auto-navigate
```

## Verdict

**Google portability battle (this run): FAIL on “logged-in product outcome”, PASS on “pipeline integrity”.**

Tokenade correctly exports and injects Google cookies from Brave. Google does not treat that jar as a live session under automated headless/proxy conditions with donor still online. Product docs should keep saying **Google often fails** for full migration; **proxy-on-donor-machine** remains the recommended multi-device pattern.

## Next session with human

Pick **one** of:

- [x] Close Brave → re-export → headed launch to Gmail  
- [ ] Host CDP proxy, you open GUI and check Gmail manually  
- [ ] Implement/test `refresh-browser` re-warm for Google and re-measure  

---

## Plan A follow-up (2026-07-10) — donor fully quit

**Preconditions checked:** no Brave process; SingletonLock/Cookie/Socket absent.

| Step | Result |
|------|--------|
| Re-export after quit | **PASS** — 80 cookies, all critical, 0 ctrl chars (`google-brave-A.tokenade`) |
| Headed Brave launch + inject | **PASS** — Visible=True, **80/80** cookies, all SID-family present in jar |
| Gmail product outcome | **FAIL** — still account chooser |

Automated signals after headed inject to `https://mail.google.com`:

```json
{
  "signed_out": true,
  "choose_account": true,
  "sign_in": true,
  "inbox": false,
  "email_visible": true,
  "snip": "Choose an account Mihir Patil mihirpatil128@gmail.com Signed out ..."
}
```

Final URL: `accounts.google.com/.../accountchooser?...&service=mail` (GlifWebSignIn).

### Updated verdict

Closing the donor **does not** fix Google session acceptance. Concurrent use was **not** the sole cause.

**Still true:** export decrypt + inject work.  
**Still false:** portable Google cookie jar → live Gmail session on a fresh Brave profile.

Likely remaining causes: server-side risk binding (device/fingerprint/TLS), incomplete session material beyond Cookies SQLite, or session already invalidated by Google after prior multi-device experiments.

### Practical product guidance

- Prefer **`tokenade proxy` on the donor machine** (cookies never leave / same TLS egress) for multi-device Google.
- Do **not** claim “Google migrate works” from cookie export alone.
- GitHub-class sites remain the stronger portability story.

---

## Correction: agent flow was wrong (user call-out 2026-07-10)

User correctly noted prior success with:

```bash
tokenade export --browser-name brave \
  --domains "google.com,accounts.google.com,mail.google.com,drive.google.com,docs.google.com" \
  -o gmail.tokenade

tokenade launch -s gmail.tokenade -u https://mail.google.com
```

### How agent tests diverged

| Aspect | Agent (wrong) | User (known-good historically) |
|--------|---------------|--------------------------------|
| Launch browser | often `-b brave` or headless | **default chrome**, headed |
| Extra flags | `--no-cloak`, `--profile-dir`, temp profiles | **none** |
| Post-nav | bounced via `accounts.google.com` | straight to mail |
| Export domains | sometimes shorter list | full list incl. drive/docs |
| CloakBrowser | assumed relevant | **`tokenade launch` never calls CloakBrowser** (flags are dead on this path) |

Also: repo `gmail.tokenade` from Jun 12 was **Firefox**-sourced (130 cookies), not Brave — closer to a “richer jar” than our 80-cookie Brave exports.

### Fixes applied after call-out

1. Removed post-inject **accounts.google.com detour** in `cmd_launch` (can poison session with Signed out chooser).
2. Re-ran **exact** user commands (export domains + `launch -s gmail.tokenade -u https://mail.google.com`).
3. Also tried **Firefox export** (174 cookies) + same launch.

### Re-test results (exact user flow)

| Source | Target | Inject | Gmail outcome |
|--------|--------|--------|---------------|
| Brave 80 cookies | default Chrome headed | 80/80 | accountchooser **Signed out** |
| Firefox 174 cookies | default Chrome headed | 174/174 | marketing `workspace.google.com/gmail` (not inbox) |

So: **flow correction was valid; outcome still not logged-in Gmail** under current automation on this machine. User’s past Linux→Windows success is not contradicted (different time, jar, target OS/browser, possibly `proxy`/`load`, fresher cookies). CloakBrowser is **not** in the current `launch` codepath — if Cloak ever mattered, it was a different command (`tokenade cloak` / load) or an older branch.

### Open hypothesis for “why it worked before for you”

- Target was **Edge/Windows** (non-Chrome DBSC) not Canary Chrome headless/headed temp profile  
- Session used **immediately** after login/export (less risk aging)  
- Different command: `proxy` / `load` / profile inject rather than CDP `launch`  
- Older launcher without accounts.google.com bounce (now removed)  

---

## Successful retest (2026-07-10) — fresh Firefox login + clean profiles

User re-logged Google in Firefox, quit Firefox, flagged ready.

### Export (user-corrected command)

```bash
tokenade export --browser-name firefox \
  --domains "google.com,accounts.google.com" \
  -o gmail.tokenade
```

| Metric | Value |
|--------|------:|
| Cookies | **178** |
| Critical | 50 (SID family present) |
| Health | **✅ HEALTHY 99.4%** |
| Control chars | **0** |
| `gmail.tokenade` | gitignored (not committed) |

### Launch targets (clean `--profile-dir`, not system Brave/Chrome)

| Flow | Result |
|------|--------|
| **Firefox → clean Brave** + Gmail | **PASS — Inbox** `Inbox (3,703) - mihirpatil128@gmail.com - Gmail` · `#inbox` · compose present |
| **Firefox → clean Chrome** (same jar, after Brave test) | **FAIL** — accountchooser **Signed out** for all identities |

### Lessons (root causes of earlier agent failures)

1. **Stale / signed-out donor cookies** — earlier Firefox jar was already “Signed out” at Google; export looked fine but auth was dead.  
2. **Dirty target profile** — system Brave had signed-out chooser state; must use **fresh profile**.  
3. **Donor still running** — Firefox open during prior export could race; quit first.  
4. **Wrong flow flags** — headless / wrong browser / accounts.google.com bounce (removed).  
5. **Chrome as target** still flaky (this run failed after Brave already used the jar — multi-use and/or Chrome risk).  

### Recommended golden path (proven this session)

```bash
# 1) Log into Google in Firefox, fully quit Firefox
tokenade export --browser-name firefox \
  --domains "google.com,accounts.google.com" \
  -o gmail.tokenade

# 2) Clean Brave (or Edge), not a profile that already has Signed out
tokenade launch -b brave -s gmail.tokenade -u https://mail.google.com \
  --profile-dir /tmp/tokenade-gmail-brave
```

**Do not** reuse the same jar on a second browser without re-export; Google multi-device will kill it.
