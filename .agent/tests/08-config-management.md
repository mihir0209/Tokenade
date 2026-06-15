# Test 08: Config File Management

## Date: 2026-06-16

## Command
```bash
tokenade config show
```

## Result
```
📋 Tokenade Config (/home/ghostrider/.tokenade/config.json)

   auto_validate: True (default)
   default_browser: brave
   default_profile: None (default)
   output_dir: None (default)
   proxy_host: 127.0.0.1 (default)
   proxy_port: 9223 (default)
   stealth_level: maximum (default)
   visible: False (default)
```

## Verification
- Config file loaded from `~/.tokenade/config.json`
- Custom values preserved (default_browser: brave)
- Default values shown for unset options
- All config options accessible via CLI

## Verdict: PASS
