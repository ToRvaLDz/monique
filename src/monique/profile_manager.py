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
        *,
        exact_config: bool = False,
    ) -> Profile | None:
        """Find the best matching profile for the given monitor fingerprint.

        Uses Jaccard similarity on descriptions (>= 0.5), then breaks ties
        by comparing the enabled/disabled state of each monitor against the
        current compositor state.

        When *exact_config* is True (GUI detect), only profiles whose every
        monitor matches the current position/scale/transform/resolution are
        returned.  When False (daemon hotplug), the best fingerprint match
        is returned regardless of current layout.
        """
        if not current_fingerprint:
            return None

        current_set = set(current_fingerprint)
        candidates: list[tuple[float, int, int, int, int, Profile]] = []

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

            # Count matching enabled states and full config matches
            enabled_matches = 0
            config_matches = 0
            total_compared = 0
            missing_enabled = 0
            ext_enabled = 0  # external monitors enabled by this profile
            if current_monitors:
                current_state = {m.description: m for m in current_monitors}
                for m in profile.monitors:
                    cur = current_state.get(m.description)
                    if cur is None:
                        # Penalise profiles with enabled monitors not connected
                        if m.enabled:
                            missing_enabled += 1
                        continue
                    total_compared += 1
                    # Count external monitors the profile would enable
                    if m.enabled and not cur.is_internal:
                        ext_enabled += 1
                    # Internal monitor disabled by clamshell: profile has it
                    # enabled but compositor disabled it — treat as match
                    if m.enabled and not cur.enabled and cur.is_internal:
                        enabled_matches += 1
                        config_matches += 1
                        continue
                    if m.enabled != cur.enabled:
                        continue
                    enabled_matches += 1
                    # Both disabled counts as config match
                    if not m.enabled and not cur.enabled:
                        config_matches += 1
                    elif (m.x == cur.x and m.y == cur.y
                            and m.scale == cur.scale
                            and m.transform == cur.transform
                            and m.width == cur.width
                            and m.height == cur.height):
                        config_matches += 1

            # In exact mode (GUI), require all compared monitors to match
            # fully, and any missing profile monitors must be disabled
            if exact_config and current_monitors and total_compared > 0:
                if missing_enabled > 0:
                    continue
                if enabled_matches != total_compared or config_matches != total_compared:
                    continue

            candidates.append((
                score, -missing_enabled, ext_enabled,
                enabled_matches, config_matches, profile,
            ))

        if not candidates:
            return None

        # Best Jaccard, fewest missing enabled, most external enabled,
        # most enabled matches, most config matches
        candidates.sort(key=lambda c: (c[0], c[1], c[2], c[3], c[4]), reverse=True)
        return candidates[0][5]
