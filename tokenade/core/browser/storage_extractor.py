"""
CDP-based storage extraction — localStorage and sessionStorage.

Extracts localStorage and sessionStorage via Chrome DevTools Protocol.
Works on all Chromium-based browsers (Chrome, Brave, Edge).

Usage:
    extractor = StorageExtractor()
    local = await extractor.extract_local_storage(cdp_session)
    session = await extractor.extract_session_storage(cdp_session)
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class StorageExtractor:
    """Extract localStorage and sessionStorage via CDP."""

    async def extract_all(
        self,
        cdp_session: Any,
        origins: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Dict[str, str]]]:
        """Extract all storage (localStorage + sessionStorage).

        Args:
            cdp_session: CDP session object (from context.new_cdp_session)
            origins: Optional list of origins to filter (e.g., ["https://mail.google.com"])

        Returns:
            Dict with "local" and "session" keys, each mapping origin → {key: value}
        """
        local = await self.extract_local_storage(cdp_session, origins)
        session = await self.extract_session_storage(cdp_session)
        return {
            "local": local,
            "session": session,
        }

    async def extract_local_storage(
        self,
        cdp_session: Any,
        origins: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, str]]:
        """Extract localStorage for all origins via CDP DOMStorage domain.

        Args:
            cdp_session: CDP session object
            origins: Optional origin filter

        Returns:
            Dict mapping origin → {key: value}
        """
        result = {}

        try:
            # Enable DOMStorage domain
            await cdp_session.send("DOMStorage.enable")

            # Get all storage keys
            resp = await cdp_session.send("DOMStorage.getDOMStorageItems", {
                "storageId": {"securityOrigin": "", "isLocalStorage": True},
            })

            # Group by origin
            if "entries" in resp:
                for entry in resp["entries"]:
                    if len(entry) >= 2:
                        key = entry[0]
                        value = entry[1]
                        # DOMStorage.getDOMStorageItems returns all localStorage
                        # We need to figure out the origin from the storageId
                        # For now, group under a single key
                        origin = "local"
                        if origin not in result:
                            result[origin] = {}
                        result[origin][key] = value

        except Exception as e:
            logger.debug(f"DOMStorage extraction failed: {e}")

        # Fallback: extract from page context via evaluate
        if not result:
            try:
                result = await self._extract_via_evaluate(cdp_session, "localStorage")
            except Exception as e:
                logger.debug(f"localStorage extraction via evaluate failed: {e}")

        return result

    async def extract_session_storage(
        self,
        cdp_session: Any,
    ) -> Dict[str, Dict[str, str]]:
        """Extract sessionStorage via page.evaluate.

        sessionStorage is per-tab, so we extract from the current page.

        Returns:
            Dict mapping origin → {key: value}
        """
        try:
            return await self._extract_via_evaluate(cdp_session, "sessionStorage")
        except Exception as e:
            logger.debug(f"sessionStorage extraction failed: {e}")
            return {}

    async def _extract_via_evaluate(
        self,
        cdp_session: Any,
        storage_type: str,
    ) -> Dict[str, Dict[str, str]]:
        """Extract storage via Runtime.evaluate.

        Args:
            cdp_session: CDP session
            storage_type: "localStorage" or "sessionStorage"

        Returns:
            Dict mapping origin → {key: value}
        """
        js = f"""
        (() => {{
            const storage = window.{storage_type};
            const items = {{}};
            for (let i = 0; i < storage.length; i++) {{
                const key = storage.key(i);
                items[key] = storage.getItem(key);
            }}
            return JSON.stringify(items);
        }})()
        """

        try:
            resp = await cdp_session.send("Runtime.evaluate", {
                "expression": js,
                "returnByValue": True,
            })

            if resp and "result" in resp:
                result = resp["result"]
                if result.get("type") == "string":
                    value = result.get("value", "{}")
                    if isinstance(value, str):
                        items = json.loads(value)
                    else:
                        items = value

                    if items:
                        # Get current origin
                        origin = await self._get_current_origin(cdp_session)
                        return {origin: items}

        except Exception as e:
            logger.debug(f"Runtime.evaluate failed for {storage_type}: {e}")

        return {}

    async def _get_current_origin(self, cdp_session: Any) -> str:
        """Get the current page origin."""
        try:
            resp = await cdp_session.send("Runtime.evaluate", {
                "expression": "window.location.origin",
                "returnByValue": True,
            })
            if resp and "result" in resp:
                return resp["result"].get("value", "unknown")
        except Exception:
            pass
        return "unknown"

    async def inject_local_storage(
        self,
        cdp_session: Any,
        storage: Dict[str, Dict[str, str]],
    ) -> int:
        """Inject localStorage into the browser via CDP.

        Args:
            cdp_session: CDP session
            storage: Dict mapping origin → {key: value}

        Returns:
            Number of items injected
        """
        injected = 0

        for origin, items in storage.items():
            for key, value in items.items():
                try:
                    await cdp_session.send("Runtime.evaluate", {
                        "expression": f'localStorage.setItem("{key}", "{value}")',
                    })
                    injected += 1
                except Exception as e:
                    logger.debug(f"Failed to inject localStorage {key}: {e}")

        return injected

    async def inject_session_storage(
        self,
        cdp_session: Any,
        storage: Dict[str, Dict[str, str]],
    ) -> int:
        """Inject sessionStorage into the browser via CDP.

        Args:
            cdp_session: CDP session
            storage: Dict mapping origin → {key: value}

        Returns:
            Number of items injected
        """
        injected = 0

        for origin, items in storage.items():
            for key, value in items.items():
                try:
                    await cdp_session.send("Runtime.evaluate", {
                        "expression": f'sessionStorage.setItem("{key}", "{value}")',
                    })
                    injected += 1
                except Exception as e:
                    logger.debug(f"Failed to inject sessionStorage {key}: {e}")

        return injected
