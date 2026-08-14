"""Local-first, hash-based Session repository synchronization."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, Optional, Protocol


@dataclass(frozen=True)
class ObjectMeta:
    name: str
    sha256: str
    size: int


@dataclass(frozen=True)
class PeerConfig:
    name: str
    transport: str
    root: str
    host: Optional[str] = None
    user: Optional[str] = None
    port: int = 22
    identity_file: Optional[str] = None
    known_hosts_file: Optional[str] = None
    require_encrypted: bool = True


class SyncTransport(Protocol):
    def probe(self) -> None:
        ...

    def list_objects(self) -> Dict[str, ObjectMeta]:
        ...

    def download(self, name: str, destination: Path) -> ObjectMeta:
        ...

    def upload_atomic(
        self, source: Path, name: str, expected_hash: Optional[str]
    ) -> ObjectMeta:
        ...

    def close(self) -> None:
        ...


class LocalTransport:
    def __init__(self, root: str):
        self.root = Path(root).expanduser().resolve()

    def probe(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def list_objects(self):
        self.probe()
        return {p.name: _meta(p) for p in self.root.glob("*.tokenade") if p.is_file()}

    def download(self, name, destination):
        _valid_name(name)
        source = self.root / name
        _atomic_copy(source, destination)
        return _meta(destination)

    def upload_atomic(self, source, name, expected_hash):
        _valid_name(name)
        destination = self.root / name
        lock = self.root / f".{name}.tokenade-sync-lock"
        owner = uuid.uuid4().hex
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, owner.encode())
        except FileExistsError as exc:
            if time.time() - lock.stat().st_mtime > 600:
                lock.unlink(missing_ok=True)
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, owner.encode())
            else:
                raise RuntimeError("remote object is locked") from exc
        os.close(fd)
        try:
            actual = _hash(destination) if destination.exists() else None
            if actual != expected_hash:
                raise RuntimeError("remote changed since plan")
            _atomic_copy(source, destination)
        finally:
            try:
                if lock.read_text() == owner:
                    lock.unlink(missing_ok=True)
            except OSError:
                pass
        return _meta(destination)

    def close(self):
        pass


class SFTPTransport:
    def __init__(self, config: PeerConfig):
        self.config = config
        self.client = None
        self.sftp = None

    def probe(self):
        import paramiko

        client = paramiko.SSHClient()
        known = self.config.known_hosts_file or str(Path.home() / ".ssh/known_hosts")
        client.load_host_keys(str(Path(known).expanduser()))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(
            self.config.host,
            port=self.config.port,
            username=self.config.user,
            key_filename=str(Path(self.config.identity_file).expanduser())
            if self.config.identity_file
            else None,
            look_for_keys=True,
            allow_agent=True,
        )
        self.client = client
        self.sftp = client.open_sftp()
        self._mkdir(self.config.root)

    def _mkdir(self, root):
        current = ""
        for part in PurePosixPath(root).parts:
            current = f"{current}/{part}" if current else part
            try:
                self.sftp.stat(current)
            except IOError:
                self.sftp.mkdir(current, mode=0o700)

    def list_objects(self):
        if not self.sftp:
            self.probe()
        result = {}
        for attr in self.sftp.listdir_attr(self.config.root):
            if attr.filename.endswith(".tokenade") and "/" not in attr.filename:
                with tempfile.NamedTemporaryFile() as temp:
                    self.sftp.get(f"{self.config.root}/{attr.filename}", temp.name)
                    result[attr.filename] = _meta(Path(temp.name), name=attr.filename)
        return result

    def download(self, name, destination):
        _valid_name(name)
        temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            self.sftp.get(f"{self.config.root}/{name}", str(temp))
            os.chmod(temp, 0o600)
            os.replace(temp, destination)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        return _meta(destination)

    def upload_atomic(self, source, name, expected_hash):
        _valid_name(name)
        remote = f"{self.config.root}/{name}"
        lock = f"{remote}.tokenade-sync-lock"
        owner = f"{uuid.uuid4().hex}:{time.time()}"
        try:
            lock_handle = self.sftp.open(lock, "wx")
            lock_handle.write(owner)
            lock_handle.close()
        except Exception as exc:
            try:
                with self.sftp.open(lock, "r") as handle:
                    existing = handle.read().decode()
                    created = float(existing.rsplit(":", 1)[-1])
                if time.time() - created <= 600:
                    raise RuntimeError("remote object is locked") from exc
                with self.sftp.open(lock, "r") as handle:
                    rechecked = handle.read().decode()
                if rechecked != existing:
                    raise RuntimeError("remote object is locked") from exc
                self.sftp.remove(lock)
                try:
                    lock_handle = self.sftp.open(lock, "wx")
                    lock_handle.write(owner)
                    lock_handle.close()
                except Exception as takeover_exc:
                    raise RuntimeError("remote object is locked") from takeover_exc
                with self.sftp.open(lock, "r") as handle:
                    if handle.read().decode() != owner:
                        raise RuntimeError("remote object is locked")
            except RuntimeError:
                raise
            except Exception as recovery_exc:
                raise RuntimeError("remote object is locked") from recovery_exc
        temporary = f"{remote}.{uuid.uuid4().hex}.tmp"
        try:
            current = self.list_objects().get(name)
            if (current.sha256 if current else None) != expected_hash:
                raise RuntimeError("remote changed since plan")
            self.sftp.put(str(source), temporary)
            self.sftp.chmod(temporary, 0o600)
            if not hasattr(self.sftp, "posix_rename"):
                raise RuntimeError("SFTP server lacks atomic POSIX rename support")
            self.sftp.posix_rename(temporary, remote)
        except Exception:
            try:
                self.sftp.remove(temporary)
            except Exception:
                pass
            raise
        finally:
            try:
                with self.sftp.open(lock, "r") as handle:
                    current_owner = handle.read().decode()
                if current_owner == owner:
                    self.sftp.remove(lock)
            except Exception:
                pass
        return _meta(source, name=name)

    def close(self):
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()


class PeerSync:
    def __init__(self, local_root: str, config_dir: Optional[str] = None):
        self.local_root = Path(local_root).expanduser().resolve()
        self.state_dir = (
            Path(config_dir or Path.home() / ".tokenade/sync").expanduser().resolve()
        )
        self.config_path = self.state_dir / "peers.json"
        self.db_path = self.state_dir / "state.sqlite3"
        self.local_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._init_db()

    def add_peer(self, config: PeerConfig):
        peers = self._peers()
        peers[config.name] = asdict(config)
        self._atomic_json(self.config_path, peers)

    def remove_peer(self, name):
        peers = self._peers()
        peers.pop(name, None)
        self._atomic_json(self.config_path, peers)
        with sqlite3.connect(self.db_path) as db:
            db.execute("DELETE FROM object_state WHERE peer=?", (name,))
            db.execute("DELETE FROM runs WHERE peer=?", (name,))

    def list_peers(self):
        return [PeerConfig(**data) for _, data in sorted(self._peers().items())]

    def plan(self, peer_name: str, direction="two-way"):
        peer = self._peer(peer_name)
        transport = self._transport(peer)
        try:
            transport.probe()
            local = self._local_manifest()
            remote = transport.list_objects()
            base = self._base(peer_name)
            names = sorted(set(local) | set(remote) | set(base))
            actions = []
            conflicts = []
            for name in names:
                lh = local.get(name).sha256 if name in local else None
                rh = remote.get(name).sha256 if name in remote else None
                bh = base.get(name)
                action = None
                if lh == rh:
                    action = "noop"
                elif direction == "push":
                    action = "push" if lh else "conflict"
                elif direction == "pull":
                    action = "pull" if rh else "conflict"
                elif bh is None:
                    action = (
                        "push"
                        if lh and not rh
                        else "pull"
                        if rh and not lh
                        else "conflict"
                    )
                elif lh is None or rh is None:
                    action = "conflict"
                elif lh == bh and rh != bh:
                    action = "pull"
                elif rh == bh and lh != bh:
                    action = "push"
                else:
                    action = "conflict"
                item = {
                    "name": name,
                    "action": action,
                    "base": bh,
                    "local": lh,
                    "remote": rh,
                }
                actions.append(item)
                if action == "conflict":
                    conflicts.append(item)
            return {
                "peer": peer_name,
                "direction": direction,
                "actions": actions,
                "conflicts": conflicts,
            }
        finally:
            transport.close()

    def run(self, peer_name, direction="two-way", dry_run=False, allow_plaintext=False):
        started = time.time()
        plan = self.plan(peer_name, direction)
        result = {
            "peer": peer_name,
            "direction": direction,
            "synced": [],
            "conflicts": plan["conflicts"],
            "errors": [],
            "dry_run": dry_run,
        }
        if dry_run:
            return result
        peer = self._peer(peer_name)
        transport = self._transport(peer)
        with self._lock():
            try:
                # Re-plan while holding the local sync lock so execution is bound
                # to the latest known local and remote hashes.
                plan = self.plan(peer_name, direction)
                result["conflicts"] = plan["conflicts"]
                transport.probe()
                for item in plan["actions"]:
                    try:
                        name = item["name"]
                        if item["action"] == "push":
                            source = self.local_root / name
                            if not source.exists() or _hash(source) != item["local"]:
                                raise RuntimeError("local changed since plan")
                            if (
                                peer.require_encrypted
                                and not allow_plaintext
                                and not _encrypted(source)
                            ):
                                raise RuntimeError("plaintext upload blocked")
                            staged_source = (
                                self.state_dir / f".{name}.{uuid.uuid4().hex}.upload"
                            )
                            try:
                                _atomic_copy(source, staged_source)
                                if _hash(staged_source) != item["local"]:
                                    raise RuntimeError("local changed during staging")
                                meta = transport.upload_atomic(
                                    staged_source, name, item["remote"]
                                )
                                if meta.sha256 != item["local"]:
                                    raise RuntimeError(
                                        "uploaded bytes differ from plan"
                                    )
                            finally:
                                staged_source.unlink(missing_ok=True)
                            self._set_base(peer_name, name, meta.sha256)
                            result["synced"].append(name)
                        elif item["action"] == "pull":
                            current = self.local_root / name
                            if (_hash(current) if current.exists() else None) != item[
                                "local"
                            ]:
                                raise RuntimeError("local changed since plan")
                            temp = self.local_root / f".{name}.{uuid.uuid4().hex}.tmp"
                            try:
                                meta = transport.download(name, temp)
                                if meta.sha256 != item["remote"]:
                                    raise RuntimeError("remote changed since plan")
                                if (
                                    peer.require_encrypted
                                    and not allow_plaintext
                                    and not _encrypted(temp)
                                ):
                                    raise RuntimeError("plaintext pull blocked")
                                from tokenade.core.importer.session_packager import (
                                    SessionPackager,
                                )

                                if not _encrypted(temp):
                                    SessionPackager().load(str(temp))
                                os.replace(temp, self.local_root / name)
                                self._set_base(peer_name, name, meta.sha256)
                                result["synced"].append(name)
                            finally:
                                temp.unlink(missing_ok=True)
                        elif item["action"] == "noop" and item["local"]:
                            self._set_base(peer_name, name, item["local"])
                        elif item["action"] == "noop":
                            self._clear_base(peer_name, name)
                    except Exception as exc:
                        result["errors"].append(
                            {"name": item["name"], "error": str(exc)}
                        )
            finally:
                transport.close()
        result["duration_ms"] = (time.time() - started) * 1000
        self._record_run(result)
        return result

    def status(self, peer_name):
        plan = self.plan(peer_name)
        return {
            "peer": peer_name,
            "local_files": len(self._local_manifest()),
            "push": sum(a["action"] == "push" for a in plan["actions"]),
            "pull": sum(a["action"] == "pull" for a in plan["actions"]),
            "conflicts": len(plan["conflicts"]),
        }

    def _transport(self, peer):
        if peer.transport == "local":
            return LocalTransport(peer.root)
        if peer.transport == "ssh":
            return SFTPTransport(peer)
        raise ValueError(f"unsupported transport: {peer.transport}")

    def _peer(self, name):
        data = self._peers().get(name)
        if not data:
            raise KeyError(f"peer not found: {name}")
        return PeerConfig(**data)

    def _peers(self):
        try:
            return (
                json.loads(self.config_path.read_text())
                if self.config_path.exists()
                else {}
            )
        except Exception as exc:
            raise RuntimeError(f"invalid sync config: {exc}")

    def _local_manifest(self):
        return {
            p.name: _meta(p) for p in self.local_root.glob("*.tokenade") if p.is_file()
        }

    def _init_db(self):
        with sqlite3.connect(self.db_path) as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS object_state(peer TEXT,name TEXT,base_hash TEXT,PRIMARY KEY(peer,name)); CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,peer TEXT,direction TEXT,started REAL,summary TEXT);"
            )
        os.chmod(self.db_path, 0o600)

    def _base(self, peer):
        with sqlite3.connect(self.db_path) as db:
            return {
                n: h
                for n, h in db.execute(
                    "SELECT name,base_hash FROM object_state WHERE peer=?", (peer,)
                )
            }

    def _set_base(self, peer, name, value):
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT OR REPLACE INTO object_state VALUES(?,?,?)", (peer, name, value)
            )

    def _clear_base(self, peer, name):
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "DELETE FROM object_state WHERE peer=? AND name=?", (peer, name)
            )

    def _record_run(self, result):
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    result["peer"],
                    result["direction"],
                    time.time(),
                    json.dumps(result),
                ),
            )

    @contextmanager
    def _lock(self):
        path = self.state_dir / "sync.lock"
        owner = f"{os.getpid()}:{uuid.uuid4().hex}"
        for attempt in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, owner.encode())
                break
            except FileExistsError as exc:
                if attempt or _pid_alive(path):
                    raise RuntimeError("sync already running") from exc
                path.unlink(missing_ok=True)
        os.close(fd)
        try:
            yield
        finally:
            try:
                if path.read_text() == owner:
                    path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _atomic_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2))
        os.chmod(temp, 0o600)
        os.replace(temp, path)


def _valid_name(name):
    if (
        not name.endswith(".tokenade")
        or Path(name).name != name
        or ".." in name
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("invalid session filename")


def _hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _meta(path, name=None):
    return ObjectMeta(name or path.name, _hash(path), path.stat().st_size)


def _atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=str(destination.parent)
    )
    os.close(fd)
    try:
        shutil.copyfile(source, temp)
        os.chmod(temp, 0o600)
        os.replace(temp, destination)
    except Exception:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _encrypted(path):
    from tokenade.core.crypto.at_rest import is_encrypted_file

    return is_encrypted_file(str(path))


def _pid_alive(path: Path) -> bool:
    try:
        os.kill(int(path.read_text().split(":", 1)[0]), 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True
