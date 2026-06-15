# Test 04: Health Check

## Date: 2026-06-16

## Test 4a: Gmail Session Health
```bash
tokenade health -s /tmp/e2e_gmail.tokenade
```
Result:
```
Status: UNHEALTHY
Health Score: 97.6%
Expires In: 19h 40m
Issues:
  • 2 expired cookies
  • 1 cookies expiring soon
Recommendations:
  • Re-export session from browser
  • Consider refreshing session
```

## Test 4b: ChatGPT Session Health
```bash
tokenade health -s /tmp/e2e_chatgpt.tokenade
```
Result:
```
Status: UNHEALTHY
Health Score: 80.6%
Issues:
  • 6 expired cookies
Recommendations:
  • Re-export session from browser
```

## Test 4c: Merged Session Health
```bash
tokenade health -s /tmp/e2e_merged.tokenade
```
Result:
```
Status: UNHEALTHY
Health Score: 92.1%
Expires In: 19h 38m
Issues:
  • 8 expired cookies
  • 1 cookies expiring soon
  • Auth status: unknown
Recommendations:
  • Re-export session from browser
  • Consider refreshing session
  • Re-login and re-export session
```

## Verdict: PASS
- Health check accurately reports cookie expiry and auth status
- Score calculations work correctly
- Recommendations are actionable
