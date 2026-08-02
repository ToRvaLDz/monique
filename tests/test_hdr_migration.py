"""Legacy hdr field migration to color_management preset when read from persistence."""

from monique.models import Profile

def _make_monitor(name: str = "DP-1", hdr: bool | None = None, cm: str = "") -> dict:
    m = {"name": name, "width": 1920, "height": 1080}
    if hdr is not None:
        m["hdr"] = hdr
    if cm:
        m["color_management"] = cm
    return m


def _make_profile(name: str = "DP-1", hdr=None, cm="") -> Profile:
    monitors = [_make_monitor(name, hdr, cm)]
    return Profile.from_dict({"name": "test", "monitors": monitors})


def test_migrates_hdr_true_without_cm():
    p = _make_profile(hdr=True, cm = "")
    assert p.monitors[0].color_management == "hdr"


def test_leaves_hdr_true_with_explicit_cm_untouched():
    p = _make_profile(hdr=True, cm = "srgb")
    assert p.monitors[0].color_management == "srgb"

    p = _make_profile(hdr=True, cm = "hdr")
    assert p.monitors[0].color_management == "hdr"

    p = _make_profile(hdr=True, cm = "auto")
    assert p.monitors[0].color_management == "auto"


def test_leaves_no_hdr_key_unchanged():
    p = _make_profile(cm = "")
    assert p.monitors[0].color_management == ""

    p = _make_profile(cm = "srgb")
    assert p.monitors[0].color_management == "srgb"

    p = _make_profile(cm = "hdr")
    assert p.monitors[0].color_management == "hdr"


def test_leaves_hdr_false_unchanged():
    p = _make_profile(hdr = False, cm = "")
    assert p.monitors[0].color_management == ""

    p = _make_profile(hdr = False, cm = "srgb")
    assert p.monitors[0].color_management == "srgb"

    p = _make_profile(hdr = False, cm = "hdr")
    assert p.monitors[0].color_management == "hdr"


def test_leaves_explicit_cm_without_hdr_unchanged():
    p = _make_profile(cm = "dcip3")
    assert p.monitors[0].color_management == "dcip3"


def test_hdr_key_not_in_loaded_monitor_dict():
    p = _make_profile(hdr = True)
    assert "hdr" not in p.monitors[0].__dataclass_fields__


def test_round_trip_preserves_migrated_value():
    p = _make_profile(hdr = True, cm = "")
    restored = Profile.from_dict(p.to_dict())
    assert restored.monitors[0].color_management == "hdr"
    assert "hdr" not in restored.to_dict()["monitors"][0]


def test_multiple_monitors_migrate_independently():
    raw = {
        "name": "multi",
        "monitors": [
            _make_monitor(hdr=True),            # → cm = "hdr"
            _make_monitor(hdr=False),           # → cm = ""
            _make_monitor(cm="srgb"),           # → cm = "srgb"
            _make_monitor(hdr=True, cm="hdr"),  # → cm = "hdr" (already set)
        ],
    }
    p = Profile.from_dict(raw)
    assert [m.color_management for m in p.monitors] == [
        "hdr", "", "srgb", "hdr",
    ]