"""
Browser Manager - Core abstraction for browser lifecycle management.

Provides a unified interface for launching, managing, and closing
browser instances across different platforms and browser types.
"""

import os
import platform
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import logging

logger = logging.getLogger(__name__)


@dataclass
class BrowserConfig:
    """Configuration for browser launch."""
    browser_type: str = "chromium"  # chromium, firefox, webkit
    headless: bool = True
    user_data_dir: Optional[str] = None
    executable_path: Optional[str] = None
    channel: Optional[str] = None  # chrome, msedge, etc.
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1920, "height": 1080})
    args: List[str] = field(default_factory=list)
    ignore_default_args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    proxy: Optional[Dict[str, str]] = None
    
    # Anti-detection flags
    disable_blink_features: bool = True
    no_sandbox: bool = True
    disable_dev_shm_usage: bool = True
    no_first_run: bool = True
    no_default_browser_check: bool = True
    
    # Fingerprint spoofing
    fingerprint: Optional[Dict] = None
    stealth_level: str = "maximum"  # basic, advanced, maximum
    
    def __post_init__(self):
        """Apply default anti-detection args if not overridden."""
        default_args = []
        if self.no_sandbox:
            default_args.append("--no-sandbox")
        if self.disable_dev_shm_usage:
            default_args.append("--disable-dev-shm-usage")
        if self.no_first_run:
            default_args.append("--no-first-run")
        if self.no_default_browser_check:
            default_args.append("--no-default-browser-check")
        if self.disable_blink_features:
            default_args.append("--disable-blink-features=AutomationControlled")
        
        # Merge with user args (user args take precedence)
        existing = set(self.args)
        for arg in default_args:
            if arg.split("=")[0] not in {a.split("=")[0] for a in existing}:
                self.args.append(arg)
        
        if "--enable-automation" not in self.ignore_default_args:
            self.ignore_default_args.append("--enable-automation")


class BrowserManager(ABC):
    """
    Abstract base class for browser management.
    
    Implementations handle specific browser automation backends
    (Playwright, Selenium, etc.)
    """
    
    def __init__(self, config: BrowserConfig):
        self.config = config
        self._context = None
        self._browser = None
        self._playwright = None
        
    @abstractmethod
    def launch(self) -> Any:
        """Launch browser and return context/page handle."""
        pass
    
    @abstractmethod
    def close(self):
        """Close browser and cleanup resources."""
        pass
    
    @abstractmethod
    def get_cookies(self, urls: Optional[List[str]] = None) -> List[Dict]:
        """Get cookies from browser context."""
        pass
    
    @abstractmethod
    def add_cookies(self, cookies: List[Dict]):
        """Add cookies to browser context."""
        pass
    
    @abstractmethod
    def navigate(self, url: str, wait_until: str = "networkidle", timeout: int = 30000) -> Any:
        """Navigate to URL and return response."""
        pass
    
    @abstractmethod
    def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript in browser context."""
        pass
    
    @property
    def is_active(self) -> bool:
        """Check if browser context is active."""
        return self._context is not None


class PlaywrightBrowserManager(BrowserManager):
    """
    Playwright-based browser manager implementation.
    Production-grade with proper error handling and resource management.
    """
    
    def __init__(self, config: BrowserConfig):
        super().__init__(config)
        self._page = None
        
    def launch(self) -> Any:
        """Launch browser using Playwright."""
        try:
            from playwright.sync_api import sync_playwright
            
            self._playwright = sync_playwright().start()
            
            launch_options = {
                "headless": self.config.headless,
                "args": self.config.args,
                "ignore_default_args": self.config.ignore_default_args,
            }
            
            if self.config.executable_path:
                launch_options["executable_path"] = self.config.executable_path
            if self.config.channel:
                launch_options["channel"] = self.config.channel
            if self.config.proxy:
                launch_options["proxy"] = self.config.proxy
            
            browser_type = getattr(self._playwright, self.config.browser_type)
            
            if self.config.user_data_dir:
                # Persistent context (saves session data)
                self._context = browser_type.launch_persistent_context(
                    user_data_dir=self.config.user_data_dir,
                    **launch_options
                )
                self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            else:
                # Non-persistent context
                self._browser = browser_type.launch(**launch_options)
                context_options = {
                    "viewport": self.config.viewport,
                }
                if self.config.env:
                    context_options["env"] = self.config.env
                self._context = self._browser.new_context(**context_options)
                self._page = self._context.new_page()
            
            # Inject stealth script if fingerprint provided
            if self.config.fingerprint:
                try:
                    from ..fingerprint.injector import inject_stealth_script
                    from ..fingerprint.manager import BrowserFingerprint
                    
                    if isinstance(self.config.fingerprint, dict):
                        fingerprint = BrowserFingerprint.from_dict(self.config.fingerprint)
                    else:
                        fingerprint = self.config.fingerprint
                    
                    inject_stealth_script(self, fingerprint, self.config.stealth_level)
                    logger.info(f"Stealth script injected at level: {self.config.stealth_level}")
                except Exception as e:
                    logger.warning(f"Failed to inject stealth script: {e}")
            
            logger.info(f"Browser launched: {self.config.browser_type}, headless={self.config.headless}")
            return self._page
            
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            self.close()
            raise
    
    def close(self):
        """Close browser and cleanup Playwright."""
        try:
            if self._context:
                self._context.close()
                self._context = None
            if self._browser:
                self._browser.close()
                self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            logger.info("Browser closed and resources cleaned up")
        except Exception as e:
            logger.warning(f"Error during browser cleanup: {e}")
    
    def get_cookies(self, urls: Optional[List[str]] = None) -> List[Dict]:
        """Get cookies from browser context."""
        if not self._context:
            raise RuntimeError("Browser not launched")
        return self._context.cookies(urls)
    
    def add_cookies(self, cookies: List[Dict]):
        """Add cookies to browser context."""
        if not self._context:
            raise RuntimeError("Browser not launched")
        self._context.add_cookies(cookies)
    
    def navigate(self, url: str, wait_until: str = "networkidle", timeout: int = 30000) -> Any:
        """Navigate to URL."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return self._page.goto(url, wait_until=wait_until, timeout=timeout)
    
    def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        return self._page.evaluate(expression)
    
    def query_selector(self, selector: str, timeout: Optional[int] = None):
        """Query element on page."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        if timeout:
            return self._page.wait_for_selector(selector, timeout=timeout)
        return self._page.query_selector(selector)
    
    def click(self, selector: str, timeout: int = 5000):
        """Click element on page."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        element = self._page.wait_for_selector(selector, timeout=timeout)
        if element:
            element.click()
        return element
    
    def fill(self, selector: str, value: str, timeout: int = 5000):
        """Fill input field."""
        if not self._page:
            raise RuntimeError("Browser not launched")
        element = self._page.wait_for_selector(selector, timeout=timeout)
        if element:
            element.fill(value)
        return element


class BrowserFactory:
    """Factory for creating browser managers."""
    
    _registry: Dict[str, type] = {
        "playwright": PlaywrightBrowserManager,
    }
    
    @classmethod
    def register(cls, name: str, manager_class: type):
        """Register a new browser manager implementation."""
        cls._registry[name] = manager_class
    
    @classmethod
    def create(cls, backend: str = "playwright", **config_kwargs) -> BrowserManager:
        """Create browser manager instance."""
        if backend not in cls._registry:
            raise ValueError(f"Unknown browser backend: {backend}. Available: {list(cls._registry.keys())}")
        
        config = BrowserConfig(**config_kwargs)
        return cls._registry[backend](config)
    
    @classmethod
    def detect_chrome_path(cls) -> Optional[str]:
        """Auto-detect Chrome executable path based on OS."""
        os_type = platform.system()
        
        paths = {
            "Windows": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ],
            "Linux": [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ],
            "Darwin": [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ],
        }
        
        for path in paths.get(os_type, []):
            if os.path.exists(path):
                return path
        return None
