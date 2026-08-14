"""Deep module for profile artifacts, safe inspection, and access policy."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version


class ArtifactError(ValueError):
    pass


class SessionPolicyError(RuntimeError):
    pass


class AccessMode(str, Enum):
    CLONE = "clone"
    EXCLUSIVE_MOVE = "exclusive_move"
    SINGLE_USE = "single_use"
    RELINK_REQUIRED = "relink_required"


ACTIVE_PURPOSES = {
    "launch", "load", "gateway", "proxy", "refresh", "test",
    "inject", "runtime", "daemon",
}


@dataclass(frozen=True)
class SessionInspection:
    site: str
    format_version: str
    auth_status: str
    created_at: str
    access_mode: AccessMode
    cookie_count: int
    token_count: int
    local_storage_origins: int
    session_storage_origins: int
    required_plugins: tuple[Dict[str, str], ...]
    artifact_count: int
    artifact_bytes: int
    artifact_owners: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "site": self.site,
            "format_version": self.format_version,
            "auth_status": self.auth_status,
            "created_at": self.created_at,
            "access_mode": self.access_mode.value,
            "cookie_count": self.cookie_count,
            "token_count": self.token_count,
            "local_storage_origins": self.local_storage_origins,
            "session_storage_origins": self.session_storage_origins,
            "required_plugins": list(self.required_plugins),
            "profile_artifacts": {
                "count": self.artifact_count,
                "uncompressed_bytes": self.artifact_bytes,
                "owners": list(self.artifact_owners),
            },
            "warnings": list(self.warnings),
        }


class ProfileArtifactManager:
    """Owns the generic artifact envelope and active-use policy."""

    SCHEMA_VERSION = 1
    MAX_ENCODED_BYTES = 96 * 1024 * 1024
    MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
    MAX_FILES = 5000

    @classmethod
    def package_plugin_payload(
        cls,
        owner: str,
        owner_version: str,
        payload: Dict[str, Any],
        *,
        tokenade_requirement: str,
        browser_families: Iterable[str] = ("chromium",),
        platforms: Iterable[str] = ("linux", "windows"),
    ) -> Dict[str, Any]:
        """Wrap a plugin-produced archive in the canonical artifact envelope."""
        cls._validate_payload(payload)
        mode = AccessMode(payload.get("access_mode", AccessMode.RELINK_REQUIRED.value))
        data = str(payload["archive_base64"])
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "artifact_id": str(uuid.uuid4()),
            "owner": {"plugin": owner, "captured_with": owner_version},
            "format": {
                "name": str(payload.get("format") or "plugin-profile"),
                "version": 1,
            },
            "access": {"mode": mode.value},
            "requirements": {
                "tokenade": tokenade_requirement,
                "plugins": [{
                    "name": owner,
                    "version": f">={owner_version}",
                    "required_at": "restore",
                }],
            },
            "compatibility": {
                "browser_families": list(browser_families),
                "platforms": list(platforms),
            },
            "supersedes": ["web_storage.local"],
            "content": {
                "media_type": "application/vnd.tokenade.profile-artifact+zip",
                "encoding": "base64",
                "compressed_size": len(base64.b64decode(data, validate=True)),
                "uncompressed_size": int(payload.get("uncompressed_size", 0)),
                "entry_count": int(payload.get("file_count", 0)),
                "sha256": str(payload["archive_sha256"]),
                "data": data,
            },
            # Temporary API 1.3 adapter metadata. Archive bytes remain canonical
            # under content.data and are reconstructed only during restore.
            "adapter_metadata": {
                key: value for key, value in payload.items()
                if key not in {"archive_base64", "archive_sha256"}
            },
        }

    @classmethod
    def inspect(cls, session: Dict[str, Any]) -> SessionInspection:
        artifacts = cls.artifacts(session)
        requirements = cls.required_plugins(session, artifacts)
        modes = [cls._artifact_mode(artifact) for artifact in artifacts]
        mode = cls._strictest_mode(modes)
        storage = session.get("storage") if isinstance(session.get("storage"), dict) else {}
        local = storage.get("local") if isinstance(storage.get("local"), dict) else {}
        temporary = storage.get("session") if isinstance(storage.get("session"), dict) else {}
        warnings = []
        if mode == AccessMode.EXCLUSIVE_MOVE:
            warnings.append("Source profile must be retired before active use")
        elif mode == AccessMode.SINGLE_USE:
            warnings.append("Local single-use enforcement cannot prevent pre-use file copies")
        elif mode == AccessMode.RELINK_REQUIRED:
            warnings.append("Target requires relinking before authentication")
        if session.get("plugin_data") and not artifacts:
            warnings.append("Legacy plugin_data requires migration before active use")
        return SessionInspection(
            site=str(session.get("site_name") or "unknown"),
            format_version=str(session.get("version") or "unknown"),
            auth_status=str(session.get("auth_status") or "unknown"),
            created_at=str(session.get("created_at") or "unknown"),
            access_mode=mode,
            cookie_count=len(session.get("cookies") or []),
            token_count=len(session.get("tokens") or []),
            local_storage_origins=len(local),
            session_storage_origins=len(temporary),
            required_plugins=tuple(requirements),
            artifact_count=len(artifacts),
            artifact_bytes=sum(int(a["content"].get("uncompressed_size", 0)) for a in artifacts),
            artifact_owners=tuple(str(a["owner"]["plugin"]) for a in artifacts),
            warnings=tuple(warnings),
        )

    @classmethod
    def preflight(
        cls,
        session: Dict[str, Any],
        *,
        purpose: str,
        acknowledge_exclusive_move: bool = False,
        allow_single_use: bool = False,
    ) -> SessionInspection:
        inspection = cls.inspect(session)
        cls._validate_requirements(session)
        if purpose not in ACTIVE_PURPOSES:
            return inspection
        if session.get("plugin_data"):
            raise SessionPolicyError("Legacy or mixed plugin_data cannot be actively replayed; create a fresh export")
        if inspection.access_mode == AccessMode.EXCLUSIVE_MOVE and not acknowledge_exclusive_move:
            raise SessionPolicyError(
                "Session is an exclusive move; retire the source and acknowledge exclusive move"
            )
        if inspection.access_mode == AccessMode.SINGLE_USE and not allow_single_use:
            raise SessionPolicyError("Session is single-use and requires an explicit local claim")
        if inspection.access_mode == AccessMode.RELINK_REQUIRED:
            raise SessionPolicyError("Session requires relinking and cannot be replayed as authenticated")
        if inspection.artifact_count and purpose in {"proxy", "gateway", "runtime"}:
            raise SessionPolicyError(
                f"{purpose} does not support persistent profile artifacts; use tokenade launch"
            )
        return inspection

    @classmethod
    def artifacts(cls, session: Dict[str, Any]) -> list[Dict[str, Any]]:
        raw = session.get("profile_artifacts") or []
        if not isinstance(raw, list):
            raise ArtifactError("profile_artifacts must be a list")
        artifacts = []
        owners = set()
        for artifact in raw:
            cls._validate_envelope(artifact)
            owner = artifact["owner"]["plugin"]
            if owner in owners:
                raise ArtifactError(f"multiple artifacts for owner {owner!r}")
            owners.add(owner)
            artifacts.append(artifact)
        return artifacts

    @classmethod
    def required_plugins(
        cls,
        session: Dict[str, Any],
        artifacts: Optional[list[Dict[str, Any]]] = None,
    ) -> list[Dict[str, str]]:
        requirements: Dict[str, Dict[str, str]] = {}
        metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
        for item in metadata.get("required_plugins", []) if isinstance(metadata.get("required_plugins", []), list) else []:
            if isinstance(item, dict) and item.get("name"):
                requirements[str(item["name"])] = {
                    "name": str(item["name"]),
                    "version": str(item.get("min_version") or item.get("version") or ""),
                    "required_at": str(item.get("required_at") or "launch"),
                }
        for artifact in artifacts if artifacts is not None else cls.artifacts(session):
            for item in artifact["requirements"].get("plugins", []):
                requirements[str(item["name"])] = {
                    "name": str(item["name"]),
                    "version": str(item.get("version") or ""),
                    "required_at": str(item.get("required_at") or "restore"),
                }
        return sorted(requirements.values(), key=lambda item: item["name"])

    @classmethod
    def restore(
        cls,
        session: Dict[str, Any],
        target_user_data: str,
        browser: str,
        *,
        allow_single_use: bool = False,
    ) -> Dict[str, Any]:
        """Stage all owner restores and expose the target only after every restore succeeds."""
        artifacts = cls.artifacts(session)
        if not artifacts:
            return {"restored": 0, "owners": []}
        target = Path(target_user_data).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with cls._target_lock(target):
            cls._recover_restore(target)
            stage_root = Path(tempfile.mkdtemp(prefix=f".{target.name}.artifacts-", dir=str(target.parent)))
            staged = stage_root / target.name
            operation = uuid.uuid4().hex
            backup = target.with_name(f".{target.name}.tokenade-backup-{operation}")
            journal = target.with_name(f".{target.name}.tokenade-restore.json")
            claimed = []
            try:
                for artifact in artifacts:
                    if cls._artifact_mode(artifact) == AccessMode.SINGLE_USE:
                        if not allow_single_use:
                            raise SessionPolicyError("single-use artifact requires an explicit claim")
                        cls._claim_single_use(str(artifact["artifact_id"]))
                        claimed.append(str(artifact["artifact_id"]))
                if target.exists():
                    shutil.copytree(target, staged)
                else:
                    staged.mkdir(parents=True)
                owners = []
                for artifact in artifacts:
                    cls._validate_target_compatibility(artifact, browser)
                    owner = str(artifact["owner"]["plugin"])
                    handler = cls._load_compatible_handler(artifact)
                    payload = dict(artifact.get("adapter_metadata") or {})
                    payload.update({
                        "archive_base64": artifact["content"]["data"],
                        "archive_sha256": artifact["content"]["sha256"],
                    })
                    package = dict(session)
                    package["plugin_data"] = {owner: payload}
                    result = handler.restore_profile_data(package, str(staged), browser)
                    if not result.success:
                        raise ArtifactError(result.error or f"{owner}: restore failed")
                    owners.append(owner)
                journal.write_text(json.dumps({
                    "target": str(target), "backup": str(backup), "stage": str(staged),
                }), encoding="utf-8")
                if target.exists():
                    os.replace(target, backup)
                os.replace(staged, target)
                journal.unlink(missing_ok=True)
                if backup.exists():
                    shutil.rmtree(backup)
                for artifact_id in claimed:
                    cls._commit_single_use(artifact_id)
                return {"restored": len(artifacts), "owners": owners}
            except Exception:
                if not target.exists() and backup.exists():
                    os.replace(backup, target)
                journal.unlink(missing_ok=True)
                for artifact_id in claimed:
                    cls._release_single_use(artifact_id)
                raise
            finally:
                shutil.rmtree(stage_root, ignore_errors=True)

    @classmethod
    def web_storage_is_superseded(cls, session: Dict[str, Any]) -> bool:
        return any("web_storage.local" in artifact.get("supersedes", []) for artifact in cls.artifacts(session))

    @classmethod
    def _validate_payload(cls, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ArtifactError("plugin artifact payload must be an object")
        data = payload.get("archive_base64")
        if not isinstance(data, str) or len(data) > cls.MAX_ENCODED_BYTES:
            raise ArtifactError("artifact payload is missing or too large")
        decoded = base64.b64decode(data, validate=True)
        if hashlib.sha256(decoded).hexdigest() != payload.get("archive_sha256"):
            raise ArtifactError("artifact checksum mismatch")
        if int(payload.get("file_count", 0)) > cls.MAX_FILES:
            raise ArtifactError("artifact contains too many files")
        if int(payload.get("uncompressed_size", 0)) > cls.MAX_UNCOMPRESSED_BYTES:
            raise ArtifactError("artifact is too large")

    @classmethod
    def _validate_envelope(cls, artifact: Any) -> None:
        if not isinstance(artifact, dict) or artifact.get("schema_version") != cls.SCHEMA_VERSION:
            raise ArtifactError("unsupported profile artifact schema")
        try:
            uuid.UUID(str(artifact["artifact_id"]))
            owner = artifact["owner"]["plugin"]
            content = artifact["content"]
            AccessMode(artifact["access"]["mode"])
            if not isinstance(owner, str) or not owner:
                raise ValueError("invalid owner")
            data = content["data"]
            if not isinstance(data, str) or len(data) > cls.MAX_ENCODED_BYTES:
                raise ValueError("invalid content")
            decoded = base64.b64decode(data, validate=True)
            if len(decoded) != int(content["compressed_size"]):
                raise ValueError("compressed size mismatch")
            if hashlib.sha256(decoded).hexdigest() != content["sha256"]:
                raise ValueError("payload checksum mismatch")
            if int(content["entry_count"]) > cls.MAX_FILES:
                raise ValueError("too many entries")
            if int(content["uncompressed_size"]) > cls.MAX_UNCOMPRESSED_BYTES:
                raise ValueError("artifact too large")
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactError(f"invalid profile artifact: {exc}") from exc

    @classmethod
    def _validate_requirements(cls, session: Dict[str, Any]) -> None:
        from tokenade import __version__
        for artifact in cls.artifacts(session):
            requirement = str(artifact.get("requirements", {}).get("tokenade") or "")
            if requirement:
                try:
                    if Version(__version__) not in SpecifierSet(requirement):
                        raise SessionPolicyError(f"artifact requires Tokenade {requirement}")
                except InvalidSpecifier as exc:
                    raise ArtifactError(f"invalid Tokenade requirement: {requirement}") from exc

    @classmethod
    def _load_compatible_handler(cls, artifact: Dict[str, Any]):
        from tokenade.core.integration.plugin_dependencies import check_runtime_dependencies
        from tokenade.core.integration.plugin_loader import PluginLoader
        owner = str(artifact["owner"]["plugin"])
        loader = PluginLoader()
        manifest = loader.get_manifest(owner)
        if not manifest or owner in loader._disabled:
            raise ArtifactError(f"required plugin is missing or disabled: {owner}")
        requirement = next(
            (item.get("version") for item in artifact["requirements"].get("plugins", []) if item.get("name") == owner),
            "",
        )
        if requirement and Version(str(manifest.get("version") or "0")) not in SpecifierSet(str(requirement)):
            raise ArtifactError(f"{owner} does not satisfy {requirement}")
        runtime = check_runtime_dependencies(manifest)
        if not runtime.ready:
            raise ArtifactError(f"{owner} runtime dependencies are unavailable")
        loaded = loader.load_by_name(owner)
        if not loaded:
            raise ArtifactError(f"required plugin failed to load: {owner}")
        from tokenade.core.integration.plugin_loader import PluginState

        if loaded.state != PluginState.ACTIVE:
            raise ArtifactError(
                f"required plugin is not active: {owner} (state: {loaded.state.value})"
            )
        return loaded.instance

    @staticmethod
    def _validate_target_compatibility(artifact: Dict[str, Any], browser: str) -> None:
        compatibility = artifact.get("compatibility") or {}
        platforms = compatibility.get("platforms") or []
        platform_name = "windows" if os.name == "nt" else "linux" if sys.platform.startswith("linux") else "darwin"
        if platforms and platform_name not in platforms:
            raise ArtifactError(f"artifact does not support platform {platform_name}")
        families = compatibility.get("browser_families") or []
        family = "chromium" if browser.lower() in {"cloak", "brave", "edge", "msedge", "chrome", "chromium", "vivaldi"} else browser.lower()
        if families and family not in families:
            raise ArtifactError(f"artifact does not support browser family {family}")

    @classmethod
    @contextmanager
    def _target_lock(cls, target: Path):
        lock = target.with_name(f".{target.name}.tokenade-lock")
        for attempt in range(2):
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, str(os.getpid()).encode("ascii"))
                os.close(fd)
                break
            except FileExistsError as exc:
                if attempt or cls._lock_owner_alive(lock):
                    raise ArtifactError(f"profile restore already in progress: {target}") from exc
                lock.unlink(missing_ok=True)
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)

    @staticmethod
    def _lock_owner_alive(lock: Path) -> bool:
        try:
            pid = int(lock.read_text(encoding="ascii"))
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except (OSError, ValueError):
            return True

    @staticmethod
    def _recover_restore(target: Path) -> None:
        journal = target.with_name(f".{target.name}.tokenade-restore.json")
        if not journal.exists():
            return
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
            backup = Path(data["backup"])
            if not target.exists() and backup.exists():
                os.replace(backup, target)
            elif target.exists() and backup.exists():
                shutil.rmtree(backup)
        finally:
            journal.unlink(missing_ok=True)

    @staticmethod
    def _claims_path() -> Path:
        return Path.home() / ".tokenade" / "artifact_claims.json"

    @classmethod
    def _read_claims(cls) -> Dict[str, str]:
        path = cls._claims_path()
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:
            return {}

    @classmethod
    @contextmanager
    def _claims_lock(cls):
        lock = cls._claims_path().with_suffix(".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise SessionPolicyError("single-use claim store is busy") from exc
        os.close(fd)
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)

    @classmethod
    def _write_claims(cls, claims: Dict[str, str]) -> None:
        path = cls._claims_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(claims, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    @classmethod
    def _claim_single_use(cls, artifact_id: str) -> None:
        with cls._claims_lock():
            claims = cls._read_claims()
            if artifact_id in claims:
                raise SessionPolicyError("single-use artifact has already been claimed or consumed")
            claims[artifact_id] = "claimed"
            cls._write_claims(claims)

    @classmethod
    def _commit_single_use(cls, artifact_id: str) -> None:
        with cls._claims_lock():
            claims = cls._read_claims()
            claims[artifact_id] = "consumed"
            cls._write_claims(claims)

    @classmethod
    def _release_single_use(cls, artifact_id: str) -> None:
        with cls._claims_lock():
            claims = cls._read_claims()
            if claims.get(artifact_id) == "claimed":
                claims.pop(artifact_id, None)
                cls._write_claims(claims)

    @staticmethod
    def _artifact_mode(artifact: Dict[str, Any]) -> AccessMode:
        return AccessMode(artifact["access"]["mode"])

    @staticmethod
    def _strictest_mode(modes: list[AccessMode]) -> AccessMode:
        priority = {
            AccessMode.CLONE: 0,
            AccessMode.EXCLUSIVE_MOVE: 1,
            AccessMode.SINGLE_USE: 2,
            AccessMode.RELINK_REQUIRED: 3,
        }
        return max(modes, key=priority.get) if modes else AccessMode.CLONE
