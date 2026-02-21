## What's New

### Bug Fixes
- Fix daemon not detecting compositor: switched systemd service from `default.target` to `graphical-session.target` so environment variables (`HYPRLAND_INSTANCE_SIGNATURE`, `SWAYSOCK`) are available
