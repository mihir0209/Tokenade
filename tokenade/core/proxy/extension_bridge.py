"""
Extension-Proxy WebSocket Bridge.

Enables real-time communication between the browser extension and the local
proxy server. The extension can push cookie updates to the proxy without
requiring a restart.
"""
import json
import asyncio
import logging
from typing import Optional, Dict, Callable, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BridgeMessage:
    """Message between extension and proxy."""
    type: str  # 'cookie_update', 'heartbeat', 'session_request', 'session_response'
    data: Dict = field(default_factory=dict)
    source: str = ""  # 'extension' or 'proxy'


class ExtensionBridge:
    """WebSocket bridge between browser extension and proxy."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 9223):
        self.host = host
        self.port = port
        self._clients: Set = set()
        self._message_handlers: Dict[str, Callable] = {}
        self._session_callback: Optional[Callable] = None
        self._running = False
    
    def on_message(self, msg_type: str, handler: Callable):
        """Register a message handler for a specific message type."""
        self._message_handlers[msg_type] = handler
    
    def on_session_update(self, callback: Callable):
        """Register callback for session updates from extension."""
        self._session_callback = callback
    
    async def start(self):
        """Start the WebSocket bridge server."""
        try:
            import websockets
        except ImportError:
            logger.error("websockets not installed. Install with: pip install websockets")
            return
        
        self._running = True
        
        async def handle_client(websocket, path=None):
            self._clients.add(websocket)
            logger.info(f"Extension connected: {websocket.remote_address}")
            
            try:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        msg = BridgeMessage(
                            type=data.get("type", "unknown"),
                            data=data.get("data", {}),
                            source="extension",
                        )
                        
                        # Handle message
                        if msg.type in self._message_handlers:
                            response = self._message_handlers[msg.type](msg)
                            if response:
                                await websocket.send(json.dumps(response))
                        
                        # Handle session updates
                        if msg.type == "cookie_update" and self._session_callback:
                            self._session_callback(msg.data)
                            
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from extension")
                        
            except Exception as e:
                logger.debug(f"Extension disconnected: {e}")
            finally:
                self._clients.discard(websocket)
                logger.info("Extension disconnected")
        
        try:
            server = await websockets.serve(handle_client, self.host, self.port)
            logger.info(f"Extension bridge listening on ws://{self.host}:{self.port}")
            
            # Keep running until stopped
            while self._running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Bridge server error: {e}")
    
    def stop(self):
        """Stop the bridge server."""
        self._running = False
    
    async def broadcast(self, message: Dict):
        """Send a message to all connected extensions."""
        if not self._clients:
            return
        
        msg = json.dumps(message)
        disconnected = set()
        
        for client in self._clients:
            try:
                await client.send(msg)
            except Exception:
                disconnected.add(client)
        
        self._clients -= disconnected
    
    def send_session_update(self, session_data: Dict):
        """Send session update to all connected extensions."""
        asyncio.create_task(self.broadcast({
            "type": "session_update",
            "data": session_data,
        }))
    
    def get_status(self) -> Dict:
        """Get bridge status."""
        return {
            "host": self.host,
            "port": self.port,
            "running": self._running,
            "connected_clients": len(self._clients),
        }
