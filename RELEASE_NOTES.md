## Highlights

Monitor changes that happen while Monique is not watching no longer leave a stale
profile in place: the daemon now re-checks the layout when the machine wakes up,
and the same check is available on demand from the CLI.

## Added

- **`monique --detect-profile`** matches the connected monitors against the saved
  profiles and applies the best one, for the cases the daemon cannot see: monitors
  plugged or unplugged while the machine is off, or while the daemon is not
  running. `--detect-profile --dry-run` prints the profile without applying it.
  (#47)
- **The daemon reacts to resume from suspend.** No hotplug event is delivered for
  a monitor changed while the machine sleeps, so the profile from before the
  suspend used to stay in place. `moniqued` now watches logind and re-matches on
  wake-up, waiting for the monitor list to settle first: outputs come back one at
  a time, and matching on a half-woken layout would apply a degraded profile and
  migrate workspaces away from monitors that are about to reappear.

## Fixed

- **`monique --current-profile` reports the profile that matches the live layout.**
  It used to return the last profile Monique itself applied, read from
  `settings.json`, so any change made outside Monique left it stale and status bar
  widgets kept showing the previous profile. It now falls back to the stored value
  only when no compositor is reachable or no profile describes the layout.
- **The PKGBUILD installs only the wheel for the version being built.** Building
  twice from the same working tree left older wheels in `dist/`, and the install
  aborted on a conflicting `/usr/bin/monique`.

## Notes

The package description and the `optdepends` now mention Niri, which has been
supported for a while but was missing from the metadata published to PyPI and AUR.
