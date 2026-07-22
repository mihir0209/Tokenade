"""
Connection Pool for SSH Transport.

Provides connection pooling for SSH/SCP connections to improve performance.
"""

import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Connection pool for SSH connections.
    
    Features:
    - Connection reuse
    - Automatic cleanup of stale connections
    - Thread-safe operations
    - Configurable pool size
    """
    
    def __init__(self, max_size: int = 10, max_idle_time: int = 300):
        """
        Initialize connection pool.
        
        Args:
            max_size: Maximum number of connections in pool
            max_idle_time: Maximum idle time before connection is closed (seconds)
        """
        self.max_size = max_size
        self.max_idle_time = max_idle_time
        self._pool: Dict[str, list] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()
    
    def get_connection(self, host: str, port: int = 22, username: str = ""):
        """
        Get a connection from the pool or create a new one.
        
        Args:
            host: SSH host
            port: SSH port
            username: SSH username
            
        Returns:
            SSH client connection
        """
        key = f"{host}:{port}:{username}"
        
        with self._lock:
            self._cleanup_if_needed()
            
            if key in self._pool and self._pool[key]:
                connection = self._pool[key].pop(0)
                if self._is_connection_alive(connection):
                    logger.debug(f"Reusing connection to {key}")
                    return connection
                else:
                    logger.debug(f"Connection to {key} is stale, creating new one")
                    self._close_connection(connection)
            
            logger.debug(f"Creating new connection to {key}")
            return self._create_connection(host, port, username)
    
    def return_connection(self, host: str, port: int, username: str, connection):
        """
        Return a connection to the pool.
        
        Args:
            host: SSH host
            port: SSH port
            username: SSH username
            connection: SSH client connection
        """
        key = f"{host}:{port}:{username}"
        
        with self._lock:
            if key not in self._pool:
                self._pool[key] = []
            
            if len(self._pool[key]) < self.max_size:
                logger.debug(f"Returning connection to pool for {key}")
                self._pool[key].append(connection)
            else:
                logger.debug(f"Pool full for {key}, closing connection")
                self._close_connection(connection)
    
    def close_all(self):
        """Close all connections in the pool."""
        with self._lock:
            for key, connections in self._pool.items():
                for conn in connections:
                    self._close_connection(conn)
            self._pool.clear()
            logger.debug("Closed all connections in pool")
    
    def _create_connection(self, host: str, port: int, username: str):
        """Create a new SSH connection."""
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                host,
                port=port,
                username=username,
                look_for_keys=True,
            )
            return client
        except ImportError:
            logger.warning("paramiko not installed")
            return None
        except Exception as e:
            logger.error(f"Failed to create connection to {host}:{port}: {e}")
            return None
    
    def _is_connection_alive(self, connection) -> bool:
        """Check if a connection is still alive."""
        if not connection:
            return False
        try:
            transport = connection.get_transport()
            if transport and transport.is_active():
                transport.send_ignore()
                return True
            return False
        except Exception:
            return False
    
    def _close_connection(self, connection):
        """Close a connection."""
        try:
            if connection:
                connection.close()
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
    
    def _cleanup_if_needed(self):
        """Cleanup stale connections if needed."""
        current_time = time.time()
        if current_time - self._last_cleanup < 60:
            return
        
        self._last_cleanup = current_time
        
        for key in list(self._pool.keys()):
            connections = self._pool[key]
            alive_connections = []
            
            for conn in connections:
                if self._is_connection_alive(conn):
                    alive_connections.append(conn)
                else:
                    self._close_connection(conn)
            
            self._pool[key] = alive_connections
            
            if not self._pool[key]:
                del self._pool[key]
        
        logger.debug("Cleaned up stale connections")


class PooledSSHTransport:
    """
    SSH transport with connection pooling.
    
    Features:
    - Connection reuse via pool
    - Automatic connection management
    - Thread-safe operations
    """
    
    _pool = ConnectionPool()
    
    def __init__(self, host: str, port: int = 22, username: str = ""):
        self.host = host
        self.port = port
        self.username = username
        self._connection = None
    
    def connect(self) -> bool:
        """Get a connection from the pool."""
        self._connection = self._pool.get_connection(
            self.host, self.port, self.username
        )
        return self._connection is not None
    
    def disconnect(self):
        """Return connection to the pool."""
        if self._connection:
            self._pool.return_connection(
                self.host, self.port, self.username, self._connection
            )
            self._connection = None
    
    def upload(self, local_path, remote_path: str) -> bool:
        """Upload file via SFTP."""
        if not self._connection:
            return False
        try:
            sftp = self._connection.open_sftp()
            sftp.put(str(local_path), remote_path)
            sftp.close()
            return True
        except Exception as e:
            logger.error(f"SFTP upload failed: {e}")
            return False
    
    def download(self, remote_path: str, local_path) -> bool:
        """Download file via SFTP."""
        if not self._connection:
            return False
        try:
            sftp = self._connection.open_sftp()
            sftp.get(remote_path, str(local_path))
            sftp.close()
            return True
        except Exception as e:
            logger.error(f"SFTP download failed: {e}")
            return False
    
    def list_remote(self, path: str):
        """List remote directory."""
        if not self._connection:
            return []
        try:
            sftp = self._connection.open_sftp()
            files = sftp.listdir(path)
            sftp.close()
            return files
        except Exception as e:
            logger.error(f"SFTP list failed: {e}")
            return []
    
    def mkdir_remote(self, path: str) -> bool:
        """Create remote directory."""
        if not self._connection:
            return False
        try:
            sftp = self._connection.open_sftp()
            sftp.mkdir(path)
            sftp.close()
            return True
        except Exception as e:
            logger.error(f"SFTP mkdir failed: {e}")
            return False
