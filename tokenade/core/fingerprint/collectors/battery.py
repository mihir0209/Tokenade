"""
Battery Collector - Collects battery status.
"""

from typing import Dict, Any
from .base import BaseCollector


class BatteryCollector(BaseCollector):
    """Collects battery status data."""

    @property
    def api_name(self) -> str:
        return "battery"

    def collect(self, browser_manager) -> Dict[str, Any]:
        """Collect battery status."""
        script = """() => {
            if (navigator.getBattery) {
                return navigator.getBattery().then(battery => ({
                    charging: battery.charging,
                    level: battery.level,
                    chargingTime: battery.chargingTime,
                    dischargingTime: battery.dischargingTime
                }));
            }
            return { charging: true, level: 1.0, chargingTime: 0, dischargingTime: Infinity };
        }"""

        try:
            result = browser_manager.evaluate(script)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def get_script_template(self) -> str:
        return """
// Battery spoofing
(function() {
    const batteryData = {
        charging: {{charging}},
        level: {{level}},
        chargingTime: {{chargingTime}},
        dischargingTime: {{dischargingTime}}
    };

    if (navigator.getBattery) {
        navigator.getBattery = function() {
            return Promise.resolve({
                charging: batteryData.charging,
                level: batteryData.level,
                chargingTime: batteryData.chargingTime,
                dischargingTime: batteryData.dischargingTime,
                addEventListener: function() {}
            });
        };
    }
})();
"""
