# Test 05: Session Management (Merge, Diff, List)

## Date: 2026-06-16

## Test 5a: Session List
```bash
tokenade sessions list -d /tmp/
```
Result:
```
Site                 Cookies    Browser      Size       Path
google               123        firefox      44.1K      e2e_gmail.tokenade
openai               31         firefox      16.7K      e2e_chatgpt.tokenade

Total: 2 sessions
```

## Test 5b: Session Merge
```bash
tokenade sessions merge /tmp/e2e_chatgpt.tokenade /tmp/e2e_gmail.tokenade -o /tmp/e2e_merged.tokenade --site-name combined
```
Result:
- Loaded 31 cookies from ChatGPT session
- Loaded 123 cookies from Gmail session
- Merged 2 sessions into `/tmp/e2e_merged.tokenade`
- Total cookies: 154 → 114 (deduped)

## Test 5c: Session Diff
```bash
tokenade diff /tmp/e2e_chatgpt.tokenade /tmp/e2e_gmail.tokenade
```
Result:
```
Cookies only in A: 29
Cookies only in B: 85
Metadata differences: ['site_name', 'created_at']
```

## Verdict: PASS
- Session list correctly shows all sessions in directory
- Session merge correctly combines and deduplicates cookies
- Session diff correctly identifies unique cookies per session
