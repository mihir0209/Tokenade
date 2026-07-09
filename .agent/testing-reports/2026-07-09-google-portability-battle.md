# Google Portability Battle Test (SUPERSEDED)

**Date:** 2026-07-09  
**Status:** **SUPERSEDED** by `.agent/results/2026-07-10-google-portability.md`

The 2026-07-09 run concluded Google rejected portable jars. Later work showed those failures were largely **process bugs** (stale cookies, dirty profiles, accounts.google bounce, Chrome targets), not a universal ban.

## Current truth (2026-07-10)

- Non-Chrome targets: **works** multi-browser + multi-device  
- Chrome-family targets: **fails** (clean profile confirmed)  
- Full recipe + commands: see results doc above  

(Original detailed FAIL log retained only as historical context below was replaced by this pointer to avoid clutter.)
