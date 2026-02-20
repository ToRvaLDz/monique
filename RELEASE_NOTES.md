## What's New

### Clamshell Mode (#2)
- Automatically disable the internal laptop display when external monitors are connected
- Manual toggle button in the toolbar for quick on/off
- Preference switch to enable automatic clamshell in the daemon
- Lid detection via UPower D-Bus: closing the lid disables the internal display, opening it re-enables it
- Safe fallback: never disables the internal display if no external monitors are available

### greetd Support
- Added greetd display manager support alongside SDDM
