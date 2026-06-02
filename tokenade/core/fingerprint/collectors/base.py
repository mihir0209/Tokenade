"""
Base Collector - Abstract base for fingerprint collectors.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseCollector(ABC):
    """Abstract base for fingerprint collectors."""
    
    @property
    @abstractmethod
    def api_name(self) -> str:
        """Name of the API being collected."""
        pass
    
    @abstractmethod
    def collect(self, browser_manager) -> Dict[str, Any]:
        """
        Collect fingerprint data from browser.
        
        Args:
            browser_manager: Browser manager with evaluate() method
            
        Returns:
            Dictionary of collected fingerprint data
        """
        pass
    
    @abstractmethod
    def get_script_template(self) -> str:
        """
        Return JavaScript template for spoofing this API.
        
        The template should contain placeholders like {{user_agent}}
        that will be replaced with actual values.
        
        Returns:
            JavaScript template string
        """
        pass
    
    def build_script(self, data: Dict[str, Any]) -> str:
        """
        Build spoofing script from collected data.
        
        Args:
            data: Collected fingerprint data
            
        Returns:
            JavaScript injection script
        """
        template = self.get_script_template()
        for key, value in data.items():
            placeholder = f"{{{{{key}}}}}"
            if isinstance(value, bool):
                str_value = "true" if value else "false"
            elif isinstance(value, (int, float)):
                str_value = str(value)
            elif isinstance(value, str):
                str_value = value
            elif isinstance(value, (list, dict)):
                import json
                str_value = json.dumps(value)
            else:
                str_value = str(value)
            template = template.replace(placeholder, str_value)
        return template
