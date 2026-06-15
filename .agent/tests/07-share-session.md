# Test 07: Session Sharing

## Date: 2026-06-16

## Command
```bash
tokenade share --session /tmp/e2e_chatgpt.tokenade --password test123 --format url
```

## Result
```
Session loaded: /tmp/e2e_chatgpt.tokenade (31 cookies)
Created share link: 6pVoHxputbbyp4M8jy8ydA (expires in 24h)

Session: /tmp/e2e_chatgpt.tokenade
Expires: 24 hours
Password protected: Yes

Share URL: tokenade://share/s6gjFAb7k8Fmt9rCcUmzTa-JXNsOKIAjavI5LVyflo...
Session ID: 6pVoHxputbbyp4M8jy8ydA
```

## Verification
- Share link created with unique session ID
- Password protection enabled (AES-256-GCM encrypted)
- 24-hour expiry set
- URL contains encrypted session data (not plaintext)

## Verdict: PASS
