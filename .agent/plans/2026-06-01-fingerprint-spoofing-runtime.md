# Implementation Plan: Fingerprint Spoofing Runtime

## Overview

Build a comprehensive fingerprint spoofing runtime that intercepts and overrides ALL JavaScript fingerprinting APIs with stealth wrappers, making the target browser indistinguishable from the source device. This prevents session invalidation when cookies are transferred across devices by ensuring the browser environment (not just cookies) matches the original.

## Scope

This is the highest-priority feature. Without it, Tokenade is just a cookie exporter/importer that fails on sites with device fingerprinting (Google, GitHub, Netflix, etc.). With it, sessions survive indefinitely because the site sees the exact same device signature.

## Types

### New Data Structures

```python
@dataclass
class StealthFingerprint(BrowserFingerprint):
    """Extended fingerprint with all spoofable APIs."""
    
    # Navigator (extended)
    pdf_viewer_enabled: bool = True
    bluetooth: bool = False
    usb: bool = False
    keyboard: bool = True
    media_capabilities: Dict = field(default_factory=dict)
    device_memory_gb: float = 8.0
    
    # Screen (extended)
    avail_width: int = 1920
    avail_height: int = 1040
    avail_left: int = 0
    avail_top: int = 0
    pixel_depth: int = 24
    
    # Window
    outer_width: int = 1920
    outer_height: int = 1080
    inner_width: int = 1920
    inner_height: int = 969
    
    # WebGL (extended)
    webgl_params: Dict = field(default_factory=dict)
    webgl_extensions: List[str] = field(default_factory=list)
    webgl_precision_formats: Dict = field(default_factory=dict)
    
    # Canvas
    canvas_hash: str = ""  # Pre-computed hash from source device
    canvas_data_url: str = ""  # toDataURL() output from source
    
    # Audio
    audio_sample_rate: float = 48000.0
    audio_channel_count: int = 2
    audio_channel_count_mode: str = "explicit"
    audio_fft_size: int = 2048
    
    # Fonts
    fonts_measured: Dict[str, Dict] = field(default_factory=dict)
    
    # Plugins (extended)
    plugins_detailed: List[Dict] = field(default_factory=list)
    mime_types: List[Dict] = field(default_factory=list)
    
    # Battery
    battery_charging: bool = True
    battery_level: float = 1.0
    
    # Permissions
    permissions: Dict[str, str] = field(default_factory=dict)
    
    # WebRTC
    webrtc_local_ips: List[str] = field(default_factory=list)
    
    # Chrome-specific
    chrome_brand: str = ""
    chrome_full_version: str = ""
    chrome_platform_version: str = ""
    
    # Automation flags to remove
    webdriver: bool = False
    chrome_runtime: bool = False
    cdc_props: List[str] = field(default_factory=list)


@dataclass
class SpoofingScript:
    """Generated JavaScript for injection."""
    script: str
    apis_covered: List[str]
    stealth_level: str  # "basic", "advanced", "maximum"
```

## Files

### New Files

- `tokenade/core/fingerprint/stealth.py` — Stealth wrapper generators and script builders
- `tokenade/core/fingerprint/collectors/` — Modular collectors for each API category
  - `navigator.py` — Navigator property collector
  - `screen.py` — Screen/window property collector
  - `webgl.py` — WebGL parameter collector
  - `canvas.py` — Canvas fingerprint collector
  - `audio.py` — AudioContext fingerprint collector
  - `fonts.py` — Font measurement collector
  - `plugins.py` — Plugin/MIME type collector
  - `webrtc.py` — WebRTC local IP collector
  - `battery.py` — Battery API collector
- `tokenade/core/fingerprint/injector.py` — Browser injection logic
- `tokenade/core/fingerprint/templates/` — JavaScript template files
  - `stealth_base.js` — Base stealth framework
  - `navigator_spoof.js` — Navigator overrides
  - `screen_spoof.js` — Screen/window overrides
  - `webgl_spoof.js` — WebGL context overrides
  - `canvas_spoof.js` — Canvas 2D overrides
  - `audio_spoof.js` — AudioContext overrides
  - `automation_cleanup.js` — Remove automation flags
- `tokenade/tests/test_stealth.py` — Unit tests for stealth wrappers
- `tokenade/tests/test_collectors.py` — Unit tests for collectors

### Modified Files

- `tokenade/core/fingerprint/manager.py` — Extend `BrowserFingerprint` to `StealthFingerprint`, add collection orchestration
- `tokenade/core/browser/manager.py` — Add `add_init_script()` integration, apply fingerprint to context
- `tokenade/core/runtime/engine.py` — Use stealth headers + TLS matching together
- `tokenade/cli.py` — Add `--collect-full-fingerprint` and `--stealth-level` flags
- `tokenade/tests/test_fingerprint.py` — Update tests for extended fingerprint

## Functions

### New Functions

```python
# tokenade/core/fingerprint/stealth.py

def generate_stealth_script(fingerprint: StealthFingerprint, level: str = "maximum") -> str:
    """Generate complete stealth injection script from fingerprint."""

def _wrap_native_override(obj_name: str, prop_name: str, value: Any) -> str:
    """Generate stealth wrapper that hides override detection."""

def _patch_toString(native_code: str) -> str:
    """Patch toString() to return native-looking code."""

def _remove_automation_flags() -> str:
    """Generate script to remove navigator.webdriver, chrome.runtime, etc."""

def _spoof_navigator(fingerprint: StealthFingerprint) -> str:
    """Generate navigator property overrides."""

def _spoof_screen(fingerprint: StealthFingerprint) -> str:
    """Generate screen/window property overrides."""

def _spoof_webgl(fingerprint: StealthFingerprint) -> str:
    """Generate WebGL context parameter overrides."""

def _spoof_canvas(fingerprint: StealthFingerprint) -> str:
    """Generate Canvas 2D pixel data overrides."""

def _spoof_audio(fingerprint: StealthFingerprint) -> str:
    """Generate AudioContext parameter overrides."""

# tokenade/core/fingerprint/injector.py

def inject_stealth_script(browser_manager, script: str) -> bool:
    """Inject stealth script into browser via add_init_script."""

def validate_injection(browser_manager) -> Dict[str, Any]:
    """Verify spoofing is active by checking overridden APIs."""

# tokenade/core/fingerprint/collectors/*.py

def collect_navigator(browser_manager) -> Dict[str, Any]:
    """Collect all navigator properties from source browser."""

def collect_screen(browser_manager) -> Dict[str, Any]:
    """Collect screen and window dimensions from source browser."""

def collect_webgl(browser_manager) -> Dict[str, Any]:
    """Collect WebGL parameters and extensions from source browser."""

def collect_canvas(browser_manager) -> Dict[str, Any]:
    """Collect canvas fingerprint (pixel hash) from source browser."""

def collect_audio(browser_manager) -> Dict[str, Any]:
    """Collect AudioContext fingerprint from source browser."""

def collect_fonts(browser_manager) -> Dict[str, Any]:
    """Collect measured font metrics from source browser."""

def collect_plugins(browser_manager) -> Dict[str, Any]:
    """Collect plugin and MIME type data from source browser."""

def collect_webrtc(browser_manager) -> Dict[str, Any]:
    """Collect WebRTC local IPs from source browser."""

def collect_battery(browser_manager) -> Dict[str, Any]:
    """Collect battery status from source browser."""
```

### Modified Functions

```python
# tokenade/core/fingerprint/manager.py

class FingerprintCollector:
    @staticmethod
    def collect_from_browser(browser_manager) -> StealthFingerprint:
        """Extended to collect ALL fingerprinting APIs."""
        # Currently collects: userAgent, screen, viewport, platform, language, timezone, hardware, WebGL, plugins
        # Extended to also collect: canvas, audio, fonts, webrtc, battery, permissions, automation flags
        
# tokenade/core/browser/manager.py

class PlaywrightBrowserManager:
    def launch(self) -> Any:
        """Extended to inject stealth script after context creation."""
        # After creating context, call context.add_init_script(stealth_script)
        
    def apply_fingerprint(self, fingerprint: StealthFingerprint):
        """New method to apply fingerprint to existing context."""
```

## Classes

### New Classes

```python
# tokenade/core/fingerprint/stealth.py

class StealthScriptBuilder:
    """Builds stealth injection scripts from fingerprint data."""
    
    def __init__(self, fingerprint: StealthFingerprint):
        self.fingerprint = fingerprint
        self.script_parts: List[str] = []
    
    def build(self, level: str = "maximum") -> str:
        """Build complete script."""
        pass
    
    def _add_base_framework(self):
        """Add stealth framework that prevents detection."""
        pass
    
    def _add_navigator_spoofs(self):
        """Add navigator property overrides."""
        pass
    
    def _add_screen_spoofs(self):
        """Add screen/window overrides."""
        pass
    
    def _add_webgl_spoofs(self):
        """Add WebGL parameter overrides."""
        pass
    
    def _add_canvas_spoofs(self):
        """Add Canvas 2D pixel data overrides."""
        pass
    
    def _add_audio_spoofs(self):
        """Add AudioContext overrides."""
        pass
    
    def _add_automation_cleanup(self):
        """Remove automation flags."""
        pass

# tokenade/core/fingerprint/collectors/base.py

class BaseCollector(ABC):
    """Abstract base for fingerprint collectors."""
    
    @abstractmethod
    def collect(self, browser_manager) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_script_template(self) -> str:
        """Return JS template for spoofing this API."""
        pass
```

### Modified Classes

```python
# tokenade/core/fingerprint/manager.py

class BrowserFingerprint:
    # Extended with all new fields from StealthFingerprint
    # to_json/from_json updated to handle new fields

class FingerprintManager:
    def save(self, name: str, fingerprint: StealthFingerprint) -> str:
        # Updated to save extended fingerprint
        
    def load(self, name: str) -> Optional[StealthFingerprint]:
        # Updated to load extended fingerprint with backward compatibility

# tokenade/core/browser/manager.py

class BrowserConfig:
    # Add fingerprint: Optional[StealthFingerprint] = None
    # Add stealth_level: str = "maximum"

class PlaywrightBrowserManager:
    # Add _stealth_script: Optional[str] = None
    # Add apply_fingerprint() method
```

## Dependencies

### New Packages

- `none` — Pure JavaScript injection, no new Python dependencies needed
- Optional: `curl-cffi` for TLS/JA3 matching (separate feature, can be added later)

### No Version Changes

All existing dependencies remain unchanged.

## Testing

### Unit Tests

- `test_stealth.py` — Test script generation, verify stealth wrappers hide overrides
- `test_collectors.py` — Test each collector returns expected data structure
- `test_injector.py` — Test injection via mocked browser manager

### Integration Tests

- Test that `navigator.webdriver` is undefined after injection
- Test that `navigator.hardwareConcurrency` matches fingerprint
- Test that canvas `toDataURL()` returns consistent hash
- Test that WebGL vendor/renderer match fingerprint
- Test that screen dimensions match fingerprint

### Validation Tests

- Run against fingerprinting services (fingerprintjs.com, amiunique.org)
- Verify score matches source device within 5%
- Test against target sites (Google, GitHub) with transferred cookies

## Implementation Order

1. **Extend BrowserFingerprint dataclass** with all new fields (backward compatible)
2. **Create collector modules** for each API category (navigator, screen, WebGL, canvas, audio, fonts, plugins, webrtc, battery)
3. **Update FingerprintCollector** to orchestrate all collectors
4. **Create JavaScript templates** for each spoof category
5. **Build StealthScriptBuilder** to assemble templates into injection script
6. **Create injector module** to integrate with PlaywrightBrowserManager
7. **Update BrowserManager** to apply fingerprint on launch
8. **Write tests** for collectors, stealth builder, and injection
9. **Validate** against fingerprinting services and target sites
10. **Update CLI** with new flags for full fingerprint collection

## Estimated Effort

- **Phase 1** (Days 1-3): Extended fingerprint dataclass + all collectors
- **Phase 2** (Days 4-7): JavaScript templates + StealthScriptBuilder
- **Phase 3** (Days 8-10): Injection integration + BrowserManager updates
- **Phase 4** (Days 11-14): Testing, validation, and refinement

**Total: ~2 weeks**

## Success Criteria

- [ ] Fingerprint from source device collected with >50 unique attributes
- [ ] All JavaScript APIs return values matching source device
- [ ] `navigator.webdriver` is undefined (not just false)
- [ ] Canvas `toDataURL()` returns consistent pixel data
- [ ] WebGL vendor/renderer match source device
- [ ] FingerprintJS score matches source within 5%
- [ ] Google/GitHub sessions survive >24 hours after transfer
- [ ] No automation flags detectable by bot detection services
