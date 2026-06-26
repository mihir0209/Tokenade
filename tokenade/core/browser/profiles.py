"""
Browser Profile Management — create, store, and manage browser profiles with unique fingerprints.

Each profile has a unique fingerprint, optional proxy, and can be used to launch browsers.
Profiles are stored in ~/.tokenade/profiles/.
"""

import json
import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

PROFILES_DIR = Path.home() / ".tokenade" / "profiles"


@dataclass
class BrowserProfile:
    """A browser profile with fingerprint and configuration."""
    name: str
    browser: str = "chromium"
    os: str = "windows"
    fingerprint: Dict[str, Any] = field(default_factory=dict)
    proxy: Optional[Dict[str, Any]] = None
    cookies: List[Dict] = field(default_factory=list)
    storage: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_used: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def save(self, profiles_dir: Optional[Path] = None) -> Path:
        """Save profile to disk."""
        base = profiles_dir or PROFILES_DIR
        base.mkdir(parents=True, exist_ok=True)
        profile_dir = base / self.name
        profile_dir.mkdir(exist_ok=True)
        profile_file = profile_dir / "profile.json"
        with open(profile_file, "w") as f:
            json.dump(asdict(self), f, indent=2)
        logger.debug(f"Profile saved: {profile_file}")
        return profile_file

    @classmethod
    def load(cls, name: str, profiles_dir: Optional[Path] = None) -> "BrowserProfile":
        """Load profile from disk."""
        base = profiles_dir or PROFILES_DIR
        profile_file = base / name / "profile.json"
        if not profile_file.exists():
            raise FileNotFoundError(f"Profile not found: {name}")
        with open(profile_file) as f:
            data = json.load(f)
        return cls(**data)


class ProfileManager:
    """Manage browser profiles."""

    def __init__(self, profiles_dir: Optional[Path] = None):
        self.profiles_dir = profiles_dir or PROFILES_DIR
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def list_profiles(self, browser: Optional[str] = None, tag: Optional[str] = None) -> List[BrowserProfile]:
        """List all profiles, optionally filtered by browser or tag."""
        profiles = []
        for profile_dir in self.profiles_dir.iterdir():
            if not profile_dir.is_dir():
                continue
            profile_file = profile_dir / "profile.json"
            if not profile_file.exists():
                continue
            try:
                profile = BrowserProfile.load(profile_dir.name, self.profiles_dir)
                if browser and profile.browser != browser:
                    continue
                if tag and tag not in profile.tags:
                    continue
                profiles.append(profile)
            except Exception as e:
                logger.warning(f"Failed to load profile {profile_dir.name}: {e}")
        return sorted(profiles, key=lambda p: p.name)

    def get_profile(self, name: str) -> Optional[BrowserProfile]:
        """Get a specific profile by name."""
        try:
            return BrowserProfile.load(name, self.profiles_dir)
        except FileNotFoundError:
            return None

    def create_profile(
        self,
        name: str,
        browser: str = "chromium",
        os_name: str = "windows",
        proxy: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
        notes: str = "",
    ) -> BrowserProfile:
        """Create a new profile with a generated fingerprint."""
        if self.get_profile(name):
            raise ValueError(f"Profile already exists: {name}")

        from tokenade.core.browser.fingerprint import FingerprintGenerator
        gen = FingerprintGenerator()
        fingerprint = gen.generate(os_name=os_name, browser=browser)

        profile = BrowserProfile(
            name=name,
            browser=browser,
            os=os_name,
            fingerprint=fingerprint,
            proxy=proxy,
            tags=tags or [],
            notes=notes,
        )
        profile.save(self.profiles_dir)
        logger.info(f"Created profile: {name} ({browser}/{os_name})")
        return profile

    def delete_profile(self, name: str) -> bool:
        """Delete a profile."""
        profile_dir = self.profiles_dir / name
        if not profile_dir.exists():
            return False
        shutil.rmtree(profile_dir)
        logger.info(f"Deleted profile: {name}")
        return True

    def update_profile(self, name: str, **kwargs) -> Optional[BrowserProfile]:
        """Update profile fields."""
        profile = self.get_profile(name)
        if not profile:
            return None
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        profile.updated_at = time.time()
        profile.save(self.profiles_dir)
        return profile

    def mark_used(self, name: str) -> None:
        """Mark a profile as recently used."""
        profile = self.get_profile(name)
        if profile:
            profile.last_used = time.time()
            profile.save(self.profiles_dir)

    def export_profile(self, name: str, output_path: str) -> Path:
        """Export profile to a zip file."""
        profile_dir = self.profiles_dir / name
        if not profile_dir.exists():
            raise FileNotFoundError(f"Profile not found: {name}")
        output = Path(output_path)
        shutil.make_archive(str(output.with_suffix("")), "zip", profile_dir)
        return output.with_suffix(".zip")

    def import_profile(self, archive_path: str, name: Optional[str] = None) -> BrowserProfile:
        """Import profile from a zip archive."""
        archive = Path(archive_path)
        if not archive.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        import zipfile
        with zipfile.ZipFile(archive, "r") as zf:
            # Find profile.json in the archive
            profile_names = [n for n in zf.namelist() if n.endswith("profile.json")]
            if not profile_names:
                raise ValueError("Invalid profile archive: no profile.json found")

            # Extract to temp dir first
            temp_dir = Path(archive).parent / f"_import_{uuid.uuid4().hex[:8]}"
            zf.extractall(temp_dir)

            # Load profile
            profile_file = temp_dir / profile_names[0]
            with open(profile_file) as f:
                data = json.load(f)

            # Use provided name or original
            if name:
                data["name"] = name
            else:
                data["name"] = archive.stem

            # Create profile
            profile = BrowserProfile(**data)
            profile.created_at = time.time()
            profile.updated_at = time.time()
            profile.save(self.profiles_dir)

            # Cleanup temp dir
            shutil.rmtree(temp_dir)

        logger.info(f"Imported profile: {profile.name}")
        return profile

    def get_recent_profiles(self, limit: int = 5) -> List[BrowserProfile]:
        """Get recently used profiles."""
        profiles = self.list_profiles()
        with_usage = [(p, p.last_used or 0) for p in profiles]
        with_usage.sort(key=lambda x: -x[1])
        return [p for p, _ in with_usage[:limit]]

    def get_stats(self) -> Dict:
        """Get profile statistics."""
        profiles = self.list_profiles()
        browsers = {}
        for p in profiles:
            browsers[p.browser] = browsers.get(p.browser, 0) + 1
        return {
            "total": len(profiles),
            "by_browser": browsers,
            "recent": len(self.get_recent_profiles()),
        }
