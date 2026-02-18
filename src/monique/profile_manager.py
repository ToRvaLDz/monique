"""Profile management: save, load, delete, list, and match profiles."""

from __future__ import annotations

from pathlib import Path

from .models import Profile
from .utils import profiles_dir, read_json, write_json


class ProfileManager:
    """Manages monitor configuration profiles stored as JSON files."""

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = directory or profiles_dir()

    def _path_for(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_")
        return self._dir / f"{safe}.json"

    def save(self, profile: Profile) -> Path:
        """Save a profile to disk. Returns the file path."""
        path = self._path_for(profile.name)
        write_json(path, profile.to_dict())
        return path

    def load(self, name: str) -> Profile | None:
        """Load a profile by name."""
        data = read_json(self._path_for(name))
        if data is None:
            return None
        return Profile.from_dict(data)

    def delete(self, name: str) -> bool:
        """Delete a profile. Returns True if it existed."""
        path = self._path_for(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_profiles(self) -> list[str]:
        """Return sorted list of profile names."""
        names = []
        for p in sorted(self._dir.glob("*.json")):
            data = read_json(p)
            if data and isinstance(data, dict):
                names.append(data.get("name", p.stem))
        return names

    def list_all(self) -> list[Profile]:
        """Load all profiles."""
        profiles = []
        for p in sorted(self._dir.glob("*.json")):
            data = read_json(p)
            if data and isinstance(data, dict):
                profiles.append(Profile.from_dict(data))
        return profiles

    def find_best_match(self, current_fingerprint: list[str]) -> Profile | None:
        """Find the best matching profile for the given monitor fingerprint.

        Uses exact match first, then Jaccard similarity >= 0.5 as fallback.
        """
        if not current_fingerprint:
            return None

        current_set = set(current_fingerprint)
        best_profile: Profile | None = None
        best_score = 0.0

        for profile in self.list_all():
            fp = profile.fingerprint
            if not fp:
                continue

            # Exact match
            if fp == current_fingerprint:
                return profile

            # Jaccard similarity
            profile_set = set(fp)
            intersection = len(current_set & profile_set)
            union = len(current_set | profile_set)
            if union == 0:
                continue
            score = intersection / union
            if score > best_score:
                best_score = score
                best_profile = profile

        if best_score >= 0.5:
            return best_profile
        return None
