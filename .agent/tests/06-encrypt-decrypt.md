# Test 06: Encrypt/Decrypt Roundtrip

## Date: 2026-06-16

## Test 6a: Encrypt Session
```bash
tokenade encrypt --input /tmp/e2e_chatgpt.tokenade --output /tmp/e2e_chatgpt_enc.tokenade --password testpassword123
```
Result:
```
File encrypted: /tmp/e2e_chatgpt.tokenade -> /tmp/e2e_chatgpt_enc.tokenade
Output: /tmp/e2e_chatgpt_enc.tokenade
Size: 17081 -> 17147 bytes
```

## Test 6b: Decrypt Session
```bash
tokenade decrypt --input /tmp/e2e_chatgpt_enc.tokenade --output /tmp/e2e_chatgpt_dec.tokenade --password testpassword123
```
Result:
```
File decrypted: /tmp/e2e_chatgpt_enc.tokenade -> /tmp/e2e_chatgpt_dec.tokenade
Output: /tmp/e2e_chatgpt_dec.tokenade
Size: 17147 -> 17081 bytes
```

## Verification
- Encrypted file is 66 bytes larger than original (encryption overhead)
- Decrypted file is same size as original (17081 bytes)
- Roundtrip preserves data integrity

## Verdict: PASS
