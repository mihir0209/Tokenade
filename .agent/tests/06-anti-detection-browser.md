# Manual Test Report — Session Rotation & Anti-Detection

**Date:** 2026-06-14
**Version:** v3.4.0

## Test 1: Login Event Detection

### Command
```bash
python -c "
from tokenade.core.importer.session_rotation import SessionRotationMonitor
import json

with open('test_sessions/google.tokenade') as f:
    session = json.load(f)

monitor = SessionRotationMonitor(site_name='google')
monitor.snapshot(session['cookies'])

# Simulate login (auth cookie modified)
new_cookies = session['cookies'] + [{'name': 'SID', 'value': 'new_value', 'domain': '.google.com'}]
event = monitor.detect_changes(new_cookies)
print(f'Event type: {event.event_type}')
print(f'Modified cookies: {event.cookies_modified}')
"
```

### Result
- **Status:** PASS
- **Output:** `login` event detected when auth cookie (SID) modified

## Test 2: CDP Artifact Removal Scripts

### Command
```bash
python -c "
from tokenade.core.antidetection.cdp_cleaner import CDPCleaner

scripts = CDPCleaner.get_stealth_scripts()
print(f'Scripts: {len(scripts)}')

init_script = CDPCleaner.get_init_script()
# Verify contains key anti-detection patterns
checks = ['navigator.webdriver', 'cdc_', 'undefined', 'plugins']
for check in checks:
    print(f'  Contains \"{check}\": {check in init_script}')
"
```

### Result
- **Status:** PASS
- **Output:** All 5 stealth scripts present, key patterns verified

## Test 3: Behavioral Mouse Path Generation

### Command
```bash
python -c "
from tokenade.core.antidetection.behavioral import BehavioralInjector

path = BehavioralInjector.generate_mouse_path((0, 0), (500, 300))
print(f'Points: {len(path)}')
print(f'Start: ({path[0][\"x\"]:.1f}, {path[0][\"y\"]:.1f})')
print(f'End: ({path[-1][\"x\"]:.1f}, {path[-1][\"y\"]:.1f})')
print(f'Delays: {min(p[\"delay_ms\"] for p in path):.1f}ms - {max(p[\"delay_ms\"] for p in path):.1f}ms')
"
```

### Result
- **Status:** PASS
- **Output:** Bezier curve path with 101 points, realistic delay range

## Test 4: Scroll Pattern Generation

### Command
```bash
python -c "
from tokenade.core.antidetection.behavioral import BehavioralInjector

scroll = BehavioralInjector.generate_scroll_pattern(1000)
print(f'Events: {len(scroll)}')
print(f'First delta: {scroll[0][\"delta_y\"]}')
print(f'Total distance: {sum(p[\"delta_y\"] for p in scroll)}')
"
```

### Result
- **Status:** PASS
- **Output:** Ease-out scroll pattern with correct total distance

## Test 5: Chromium Fork Detection

### Command
```bash
python -c "
from tokenade.core.importer.chromium_forks import ChromiumForkDetector

detector = ChromiumForkDetector()
forks = detector.detect_all()
print(f'Detected: {len(forks)} browser(s)')
for fork in forks:
    print(f'  {fork.name}: {len(fork.profile_dirs)} profile(s)')
"
```

### Result
- **Status:** PASS
- **Output:** Brave detected with 1 profile (Opera/Arc/Vivaldi not installed)

## Test 6: Mobile Extractor (No Device)

### Command
```bash
python -c "
from tokenade.core.importer.mobile_extractor import MobileExtractor

extractor = MobileExtractor()
print(f'ADB available: {extractor.is_available()}')
print(f'Devices: {extractor.list_devices()}')
cookies = extractor.extract_chrome()
print(f'Chrome cookies: {len(cookies)} (expected 0)')
"
```

### Result
- **Status:** PASS
- **Output:** Graceful fallback when ADB not installed
