"""Enabled state is forced through IPC after a Niri apply.

`niri msg output <name> on|off` leaves a temporary override that beats the
config file until that output's block in the file changes.  An idle script
running ``output HDMI-A-1 on`` therefore kept the Samsung lit after the user
re-applied a profile that turns it off: the block was already ``off``, so
Niri saw no change and kept the override.
"""

import json

from monique.models import MonitorConfig, Profile
from monique.niri import NiriIPC


class _RecordingNiri(NiriIPC):
    """NiriIPC whose socket is replaced by a live-state stub."""

    def __init__(self, live: list[MonitorConfig]) -> None:
        super().__init__()
        self._live = live
        self.sent: list[dict] = []

    def get_monitors(self) -> list[MonitorConfig]:
        return self._live

    def _request(self, msg: str):
        self.sent.append(json.loads(msg))
        return "Applied"


def _mon(name: str, desc: str, enabled: bool = True) -> MonitorConfig:
    return MonitorConfig(name=name, description=desc, enabled=enabled)


def test_stale_override_is_replaced():
    live = [_mon("DP-2", "LG"), _mon("HDMI-A-1", "Samsung")]
    profile = Profile(name="LG+AOC", monitors=[
        _mon("DP-2", "LG"), _mon("HDMI-9", "Samsung", enabled=False),
    ])
    ipc = _RecordingNiri(live)

    ipc._sync_output_power(profile)

    # Il connettore è quello live, non quello (magari vecchio) del profilo
    assert ipc.sent == [{"Output": {"output": "HDMI-A-1", "action": "Off"}}]


def test_disabled_output_is_turned_back_on():
    live = [_mon("DP-2", "LG"), _mon("HDMI-A-1", "Samsung", enabled=False)]
    profile = Profile(name="Full", monitors=[_mon("DP-2", "LG"), _mon("HDMI-A-1", "Samsung")])
    ipc = _RecordingNiri(live)

    ipc._sync_output_power(profile)

    assert ipc.sent == [{"Output": {"output": "HDMI-A-1", "action": "On"}}]


def test_matching_and_disconnected_outputs_are_left_alone():
    """No override where the config already agrees, none for absent monitors."""
    live = [_mon("DP-2", "LG")]
    profile = Profile(name="p", monitors=[_mon("DP-2", "LG"), _mon("HDMI-A-1", "Samsung")])
    ipc = _RecordingNiri(live)

    ipc._sync_output_power(profile)

    assert ipc.sent == []


def test_ipc_failure_does_not_break_the_apply():
    class _Broken(_RecordingNiri):
        def get_monitors(self):
            raise OSError("socket gone")

    _Broken([])._sync_output_power(Profile(name="p", monitors=[_mon("DP-2", "LG")]))
