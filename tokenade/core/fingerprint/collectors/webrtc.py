"""
WebRTC Collector - Collects WebRTC local IP data.
"""

from typing import Dict, Any
from .base import BaseCollector


class WebRTCCollector(BaseCollector):
    """Collects WebRTC local IP data."""
    
    @property
    def api_name(self) -> str:
        return "webrtc"
    
    def collect(self, browser_manager) -> Dict[str, Any]:
        """Collect WebRTC IPs."""
        script = """() => {
            return new Promise((resolve) => {
                const ips = [];
                const RTCPeerConnection = window.RTCPeerConnection || 
                    window.mozRTCPeerConnection || window.webkitRTCPeerConnection;
                
                if (!RTCPeerConnection) {
                    resolve({ ips: [] });
                    return;
                }
                
                const pc = new RTCPeerConnection({
                    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
                });
                
                pc.createDataChannel('');
                
                pc.onicecandidate = function(e) {
                    if (!e.candidate) {
                        pc.close();
                        resolve({ ips: ips });
                        return;
                    }
                    
                    const ipMatch = /([0-9]{1,3}\\.){3}[0-9]{1,3}/.exec(e.candidate.candidate);
                    if (ipMatch && !ips.includes(ipMatch[0])) {
                        ips.push(ipMatch[0]);
                    }
                };
                
                pc.createOffer().then(o => pc.setLocalDescription(o));
                
                // Timeout after 3 seconds
                setTimeout(() => {
                    pc.close();
                    resolve({ ips: ips });
                }, 3000);
            });
        }"""
        
        try:
            result = browser_manager.evaluate(script)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            return {}
    
    def get_script_template(self) -> str:
        return """
// WebRTC spoofing - hide local IPs
(function() {
    const RTCPeerConnection = window.RTCPeerConnection || 
        window.mozRTCPeerConnection || window.webkitRTCPeerConnection;
    
    if (!RTCPeerConnection) return;
    
    const origCreateOffer = RTCPeerConnection.prototype.createOffer;
    RTCPeerConnection.prototype.createOffer = function() {
        return origCreateOffer.apply(this, arguments).then(offer => {
            if (offer.sdp) {
                offer.sdp = offer.sdp.replace(/([0-9]{1,3}\\.){3}[0-9]{1,3}/g, '0.0.0.0');
            }
            return offer;
        });
    };
    
    const origSetLocalDescription = RTCPeerConnection.prototype.setLocalDescription;
    RTCPeerConnection.prototype.setLocalDescription = function(desc) {
        if (desc && desc.sdp) {
            desc.sdp = desc.sdp.replace(/([0-9]{1,3}\\.){3}[0-9]{1,3}/g, '0.0.0.0');
        }
        return origSetLocalDescription.apply(this, arguments);
    };
})();
"""
