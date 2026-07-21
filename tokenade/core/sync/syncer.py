"""
Session Sync - Synchronize sessions across machines.

Provides encrypted synchronization of session files between
multiple machines using various transport backends.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SyncConfig:
    """Configuration for session synchronization."""
    
    remote_host: str = ""
    remote_port: int = 22
    remote_path: str = "~/.tokenade/sessions"
    local_path: str = "~/.tokenade/sessions"
    encryption_key: Optional[str] = None
    auto_sync: bool = False
    sync_interval: int = 300
    conflict_resolution: str = "newest"  # newest, oldest, local, remote
    exclude_patterns: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncConfig':
        return cls(
            remote_host=data.get("remote_host", ""),
            remote_port=data.get("remote_port", 22),
            remote_path=data.get("remote_path", "~/.tokenade/sessions"),
            local_path=data.get("local_path", "~/.tokenade/sessions"),
            encryption_key=data.get("encryption_key"),
            auto_sync=data.get("auto_sync", False),
            sync_interval=data.get("sync_interval", 300),
            conflict_resolution=data.get("conflict_resolution", "newest"),
            exclude_patterns=data.get("exclude_patterns", []),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "remote_host": self.remote_host,
            "remote_port": self.remote_port,
            "remote_path": self.remote_path,
            "local_path": self.local_path,
            "encryption_key": self.encryption_key,
            "auto_sync": self.auto_sync,
            "sync_interval": self.sync_interval,
            "conflict_resolution": self.conflict_resolution,
            "exclude_patterns": self.exclude_patterns,
        }


@dataclass
class SyncResult:
    """Result of a sync operation."""
    
    synced: List[str] = field(default_factory=list)
    conflicts: List[Dict[str, str]] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)
    direction: str = ""  # push, pull, bidirectional
    duration_ms: float = 0
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "synced": self.synced,
            "conflicts": self.conflicts,
            "errors": self.errors,
            "direction": self.direction,
            "duration_ms": self.duration_ms,
            "success": self.success,
        }


class SyncTransport:
    """Base class for sync transport backends."""
    
    def connect(self) -> bool:
        raise NotImplementedError
    
    def disconnect(self) -> None:
        raise NotImplementedError
    
    def upload(self, local_path: Path, remote_path: str) -> bool:
        raise NotImplementedError
    
    def download(self, remote_path: str, local_path: Path) -> bool:
        raise NotImplementedError
    
    def list_remote(self, path: str) -> List[str]:
        raise NotImplementedError


class SSHTransport(SyncTransport):
    """SSH/SCP transport backend using paramiko."""
    
    def __init__(self, host: str, port: int = 22, username: str = ""):
        self.host = host
        self.port = port
        self.username = username
        self._client = None
    
    def connect(self) -> bool:
        try:
            import paramiko
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client.connect(
                self.host,
                port=self.port,
                username=self.username,
                look_for_keys=True,
            )
            return True
        except ImportError:
            logger.warning("paramiko not installed, SSH transport unavailable")
            return False
        except Exception as e:
            logger.error(f"SSH connection failed: {e}")
            return False
    
    def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
    
    def upload(self, local_path: Path, remote_path: str) -> bool:
        if not self._client:
            return False
        try:
            sftp = self._client.open_sftp()
            sftp.put(str(local_path), remote_path)
            sftp.close()
            return True
        except Exception as e:
            logger.error(f"SFTP upload failed: {e}")
            return False
    
    def download(self, remote_path: str, local_path: Path) -> bool:
        if not self._client:
            return False
        try:
            sftp = self._client.open_sftp()
            sftp.get(remote_path, str(local_path))
            sftp.close()
            return True
        except Exception as e:
            logger.error(f"SFTP download failed: {e}")
            return False
    
    def list_remote(self, path: str) -> List[str]:
        if not self._client:
            return []
        try:
            sftp = self._client.open_sftp()
            files = sftp.listdir(path)
            sftp.close()
            return files
        except Exception as e:
            logger.error(f"SFTP list failed: {e}")
            return []


class SubprocessSSHTransport(SyncTransport):
    """SSH/SCP transport using subprocess (no paramiko dependency)."""
    
    def __init__(self, host: str, port: int = 22, username: str = ""):
        self.host = host
        self.port = port
        self.username = username
    
    def connect(self) -> bool:
        """Test SSH connection."""
        import subprocess
        
        remote = self._remote_prefix()
        cmd = ["ssh", "-p", str(self.port), "-o", "BatchMode=yes", remote, "echo ok"]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return True
            if "Host key verification failed" in result.stderr:
                logger.warning("SSH host key verification failed; add host key manually")
            return False
        except FileNotFoundError:
            logger.error("ssh binary not found")
            return False
        except subprocess.TimeoutExpired:
            logger.error("SSH connection timed out")
            return False
    
    def disconnect(self) -> None:
        pass
    
    def upload(self, local_path: Path, remote_path: str) -> bool:
        import subprocess
        
        remote = self._remote_prefix()
        cmd = [
            "scp",
            "-P", str(self.port),
            "-r",
            str(local_path),
            f"{remote}:{remote_path}",
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                logger.error(f"SCP upload failed: {result.stderr}")
            return result.returncode == 0
        except Exception as e:
            logger.error(f"SCP upload failed: {e}")
            return False
    
    def download(self, remote_path: str, local_path: Path) -> bool:
        import subprocess
        
        remote = self._remote_prefix()
        cmd = [
            "scp",
            "-P", str(self.port),
            "-r",
            f"{remote}:{remote_path}",
            str(local_path),
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                logger.error(f"SCP download failed: {result.stderr}")
            return result.returncode == 0
        except Exception as e:
            logger.error(f"SCP download failed: {e}")
            return False
    
    def list_remote(self, path: str) -> List[str]:
        import subprocess
        
        remote = self._remote_prefix()
        cmd = [
            "ssh",
            "-p", str(self.port),
            remote,
            f"ls {path} 2>/dev/null || echo ''",
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                output = result.stdout.strip()
                if not output:
                    return []
                return output.split("\n")
            return []
        except Exception as e:
            logger.error(f"SSH list failed: {e}")
            return []
    
    def mkdir_remote(self, path: str) -> bool:
        """Create remote directory if it doesn't exist."""
        import subprocess
        
        remote = self._remote_prefix()
        cmd = [
            "ssh",
            "-p", str(self.port),
            remote,
            f"mkdir -p {path}",
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"SSH mkdir failed: {e}")
            return False
    
    def _remote_prefix(self) -> str:
        """Get remote prefix for SSH/SCP commands."""
        if self.username:
            return f"{self.username}@{self.host}"
        return self.host


class RsyncTransport(SyncTransport):
    """rsync transport backend."""
    
    def __init__(self, host: str, port: int = 22, username: str = ""):
        self.host = host
        self.port = port
        self.username = username
    
    def connect(self) -> bool:
        return True
    
    def disconnect(self) -> None:
        pass
    
    def upload(self, local_path: Path, remote_path: str) -> bool:
        import subprocess
        
        remote = f"{self.username}@{self.host}:{remote_path}" if self.username else f"{self.host}:{remote_path}"
        
        cmd = [
            "rsync",
            "-avz",
            "-e", f"ssh -p {self.port}",
            str(local_path),
            remote,
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"rsync upload failed: {e}")
            return False
    
    def download(self, remote_path: str, local_path: Path) -> bool:
        import subprocess
        
        remote = f"{self.username}@{self.host}:{remote_path}" if self.username else f"{self.host}:{remote_path}"
        
        cmd = [
            "rsync",
            "-avz",
            "-e", f"ssh -p {self.port}",
            remote,
            str(local_path),
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"rsync download failed: {e}")
            return False
    
    def list_remote(self, path: str) -> List[str]:
        import subprocess
        
        remote = f"{self.username}@{self.host}:{path}" if self.username else f"{self.host}:{path}"
        
        cmd = [
            "ssh",
            "-p", str(self.port),
            remote,
            f"ls {path}",
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return result.stdout.strip().split("\n")
            return []
        except Exception as e:
            logger.error(f"SSH list failed: {e}")
            return []


class SessionSyncer:
    """
    Synchronizes session files across machines.
    
    Supports:
    - SSH/SCP transport
    - rsync transport
    - Local directory sync
    - Encrypted transport
    - Conflict resolution (newest, oldest, local, remote)
    - File hashing for change detection
    """
    
    def __init__(self, config: Optional[SyncConfig] = None):
        self.config = config or SyncConfig()
        self._local_dir = Path(os.path.expanduser(self.config.local_path))
        self._remote_dir = Path(os.path.expanduser(self.config.remote_path))
    
    def push(self, session_files: Optional[List[str]] = None) -> SyncResult:
        """
        Push sessions to remote machine.
        
        Args:
            session_files: Specific files to push, or None for all
            
        Returns:
            SyncResult with operation details
        """
        start = time.time()
        result = SyncResult(direction="push")
        
        try:
            files = self._resolve_local_files(session_files)
            manifest = self._create_manifest(files)
            
            for file_path in files:
                try:
                    self._push_file(file_path)
                    result.synced.append(str(file_path))
                except Exception as e:
                    result.errors.append({
                        "file": str(file_path),
                        "error": str(e),
                    })
            
            result.duration_ms = (time.time() - start) * 1000
            return result
            
        except Exception as e:
            result.errors.append({"error": str(e)})
            result.duration_ms = (time.time() - start) * 1000
            return result
    
    def pull(self, session_files: Optional[List[str]] = None) -> SyncResult:
        """
        Pull sessions from remote machine.
        
        Args:
            session_files: Specific files to pull, or None for all
            
        Returns:
            SyncResult with operation details
        """
        start = time.time()
        result = SyncResult(direction="pull")
        
        try:
            files = self._resolve_remote_files(session_files)
            
            for file_path in files:
                try:
                    self._pull_file(file_path)
                    result.synced.append(str(file_path))
                except Exception as e:
                    result.errors.append({
                        "file": str(file_path),
                        "error": str(e),
                    })
            
            result.duration_ms = (time.time() - start) * 1000
            return result
            
        except Exception as e:
            result.errors.append({"error": str(e)})
            result.duration_ms = (time.time() - start) * 1000
            return result
    
    def bidirectional(self) -> SyncResult:
        """
        Perform bidirectional sync with conflict resolution.
        
        Returns:
            SyncResult with operation details
        """
        start = time.time()
        result = SyncResult(direction="bidirectional")
        
        try:
            local_files = self._resolve_local_files()
            remote_files = self._resolve_remote_files()
            
            local_manifest = self._create_manifest(local_files)
            remote_manifest = self._create_manifest(remote_files)
            
            conflicts, to_push, to_pull = self._detect_changes(
                local_manifest, remote_manifest
            )
            
            for file_path in to_push:
                try:
                    self._push_file(file_path)
                    result.synced.append(f"push:{file_path}")
                except Exception as e:
                    result.errors.append({
                        "file": str(file_path),
                        "error": str(e),
                        "direction": "push",
                    })
            
            for file_path in to_pull:
                try:
                    self._pull_file(file_path)
                    result.synced.append(f"pull:{file_path}")
                except Exception as e:
                    result.errors.append({
                        "file": str(file_path),
                        "error": str(e),
                        "direction": "pull",
                    })
            
            for conflict in conflicts:
                resolved = self._resolve_conflict(conflict)
                if resolved:
                    result.synced.append(f"resolved:{conflict['name']}")
                else:
                    result.conflicts.append(conflict)
            
            result.duration_ms = (time.time() - start) * 1000
            return result
            
        except Exception as e:
            result.errors.append({"error": str(e)})
            result.duration_ms = (time.time() - start) * 1000
            return result
    
    def status(self) -> Dict[str, Any]:
        """Get sync status and pending changes."""
        local_files = self._resolve_local_files()
        remote_files = self._resolve_remote_files()
        
        local_manifest = self._create_manifest(local_files)
        remote_manifest = self._create_manifest(remote_files)
        
        conflicts, to_push, to_pull = self._detect_changes(
            local_manifest, remote_manifest
        )
        
        return {
            "local_files": len(local_files),
            "remote_files": len(remote_files),
            "pending_push": len(to_push),
            "pending_pull": len(to_pull),
            "conflicts": len(conflicts),
            "config": self.config.to_dict(),
        }
    
    def _get_transport(self) -> SyncTransport:
        """Get the appropriate transport backend."""
        host = self.config.remote_host
        port = self.config.remote_port
        
        # Try paramiko first
        try:
            import paramiko
            transport = SSHTransport(host, port)
            if transport.connect():
                return transport
        except ImportError:
            pass
        
        # Fall back to subprocess SSH
        transport = SubprocessSSHTransport(host, port)
        if transport.connect():
            return transport
        
        # Try rsync as last resort
        return RsyncTransport(host, port)
    
    def _resolve_local_files(self, patterns: Optional[List[str]] = None) -> List[Path]:
        """Resolve local session files."""
        if not self._local_dir.exists():
            return []
        
        files = list(self._local_dir.glob("*.tokenade"))
        
        for pattern in self.config.exclude_patterns:
            files = [f for f in files if not f.match(pattern)]
        
        return files
    
    def _resolve_remote_files(self, patterns: Optional[List[str]] = None) -> List[Path]:
        """Resolve remote session files via SSH."""
        transport = self._get_transport()
        
        try:
            remote_path = os.path.expanduser(self.config.remote_path)
            
            # Create remote directory if it doesn't exist
            if isinstance(transport, SubprocessSSHTransport):
                transport.mkdir_remote(remote_path)
            
            # List remote files
            remote_files = transport.list_remote(remote_path)
            
            # Filter for .tokenade files
            result = []
            for filename in remote_files:
                if filename.endswith(".tokenade"):
                    # Create a Path-like object for remote files
                    result.append(Path(remote_path) / filename)
            
            return result
        except Exception as e:
            logger.error(f"Failed to list remote files: {e}")
            return []
        finally:
            transport.disconnect()
    
    def _create_manifest(self, files: List[Path]) -> Dict[str, Dict]:
        """Create manifest with file hashes."""
        manifest = {}
        for f in files:
            if f.exists():
                stat = f.stat()
                manifest[f.name] = {
                    "path": str(f),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "hash": self._hash_file(f),
                }
        return manifest
    
    def _hash_file(self, path: Path) -> str:
        """Calculate SHA-256 hash of file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _detect_changes(
        self,
        local_manifest: Dict,
        remote_manifest: Dict,
    ) -> tuple:
        """Detect what needs to be synced."""
        conflicts = []
        to_push = []
        to_pull = []
        
        local_names = set(local_manifest.keys())
        remote_names = set(remote_manifest.keys())
        
        for name in local_names - remote_names:
            to_push.append(Path(local_manifest[name]["path"]))
        
        for name in remote_names - local_names:
            to_pull.append(Path(remote_manifest[name]["path"]))
        
        for name in local_names & remote_names:
            local_hash = local_manifest[name]["hash"]
            remote_hash = remote_manifest[name]["hash"]
            
            if local_hash != remote_hash:
                local_mtime = local_manifest[name]["mtime"]
                remote_mtime = remote_manifest[name]["mtime"]
                
                conflicts.append({
                    "name": name,
                    "local_path": local_manifest[name]["path"],
                    "remote_path": remote_manifest[name]["path"],
                    "local_mtime": local_mtime,
                    "remote_mtime": remote_mtime,
                    "local_hash": local_hash,
                    "remote_hash": remote_hash,
                })
        
        return conflicts, to_push, to_pull
    
    def _resolve_conflict(self, conflict: Dict) -> bool:
        """Resolve a sync conflict based on config."""
        resolution = self.config.conflict_resolution
        
        if resolution == "newest":
            if conflict["local_mtime"] > conflict["remote_mtime"]:
                self._push_file(Path(conflict["local_path"]))
            else:
                self._pull_file(Path(conflict["remote_path"]))
            return True
        
        elif resolution == "oldest":
            if conflict["local_mtime"] < conflict["remote_mtime"]:
                self._push_file(Path(conflict["local_path"]))
            else:
                self._pull_file(Path(conflict["remote_path"]))
            return True
        
        elif resolution == "local":
            self._push_file(Path(conflict["local_path"]))
            return True
        
        elif resolution == "remote":
            self._pull_file(Path(conflict["remote_path"]))
            return True
        
        return False
    
    def _push_file(self, file_path: Path) -> None:
        """Push a single file to remote."""
        transport = self._get_transport()
        try:
            remote_path = os.path.expanduser(self.config.remote_path)
            remote_file = f"{remote_path}/{file_path.name}"
            
            if transport.upload(file_path, remote_file):
                logger.info(f"Pushed {file_path.name} to {self.config.remote_host}:{remote_path}")
            else:
                raise Exception(f"Failed to upload {file_path.name}")
        finally:
            transport.disconnect()
    
    def _pull_file(self, file_path: Path) -> None:
        """Pull a single file from remote."""
        transport = self._get_transport()
        try:
            local_file = self._local_dir / file_path.name
            
            if transport.download(str(file_path), local_file):
                logger.info(f"Pulled {file_path.name} from {self.config.remote_host}")
            else:
                raise Exception(f"Failed to download {file_path.name}")
        finally:
            transport.disconnect()
