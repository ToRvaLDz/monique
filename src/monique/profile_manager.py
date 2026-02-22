"""Profile management: save, load, delete, list, and match profiles."""

from __future__ import annotations

from pathlib import Path

from .models import MonitorConfig, Profile
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

    def find_best_match(
        self,
        current_fingerprint: list[str],
        current_monitors: list[MonitorConfig] | None = None,
    ) -> Profile | None:
        """Find the best matching profile for the given monitor fingerprint.

        Uses Jaccard similarity on descriptions (>= 0.5), then breaks ties
        by comparing the enabled/disabled state of each monitor against the
        current compositor state.
        """
        if not current_fingerprint:
            return None

        current_set = set(current_fingerprint)
        candidates: list[tuple[float, int, Profile]] = []

        for profile in self.list_all():
            fp = profile.fingerprint
            if not fp:
                continue

            # Jaccard similarity
            profile_set = set(fp)
            intersection = len(current_set & profile_set)
            union = len(current_set | profile_set)
            if union == 0:
                continue
            score = intersection / union
            if score < 0.5:
                continue

            # Count matching enabled states as tiebreaker
            enabled_matches = 0
            if current_monitors:
                current_state = {m.description: m.enabled for m in current_monitors}
                for m in profile.monitors:
                    if m.description in current_state:
                        if m.enabled == current_state[m.description]:
                            enabled_matches += 1

            candidates.append((score, enabled_matches, profile))

        if not candidates:
            return None

        # Best Jaccard first, then most enabled-state matches
        candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
        return candidates[0][2]
