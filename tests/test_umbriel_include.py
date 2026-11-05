"""config.toml di Umbriel: l'include di monitors.toml va tenuto allineato."""

import json
import shutil
import subprocess
import tomllib

import pytest

from monique import utils
from monique.config_paths import UMBRIEL, compositor_config_paths
from monique.umbriel_config import (
    MARKER_PREFIX,
    UmbrielConfigError,
    ensure_umbriel_include,
)

PACKAGED = """\
# Packaged Umbriel config
[include]
files = []

[include.optional]
files = []

[general]
xwayland = true

[keybinds]
"Super+Return" = "spawn foot"

# [output.DP-1]
# mode = "2560x1440@144"
"""


@pytest.fixture
def cfg(isolated_config):
    """The umbriel config dir; config.toml is not created."""
    return isolated_config / "umbriel"


@pytest.fixture
def packaged(isolated_config, monkeypatch):
    """A packaged config reachable through XDG_CONFIG_DIRS."""
    root = isolated_config / "system"
    (root / "umbriel").mkdir(parents=True)
    (root / "umbriel" / "config.toml").write_text(PACKAGED, encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(root))
    monkeypatch.setenv("XDG_DATA_DIRS", str(isolated_config / "nothing"))
    monkeypatch.setattr("monique.umbriel_config.SYSTEM_DATA_DIRS", ())
    return root / "umbriel" / "config.toml"


@pytest.fixture
def no_packaged(isolated_config, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(isolated_config / "nothing"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(isolated_config / "nothing"))
    monkeypatch.setattr("monique.umbriel_config.SYSTEM_DATA_DIRS", ())


def _write(cfg, text):
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.toml").write_text(text, encoding="utf-8")
    return cfg / "config.toml"


def _load(path):
    return tomllib.loads(path.read_text(encoding="utf-8"))


# ── no config.toml yet ───────────────────────────────────────────────────

def test_packaged_config_is_copied_then_the_include_is_added(cfg, packaged):
    assert ensure_umbriel_include() is True

    data = _load(cfg / "config.toml")
    assert data["include"]["optional"]["files"] == ["monitors.toml"]
    # nulla del config pacchettizzato va perso: senza, la sessione perde i tasti
    assert data["keybinds"] == {"Super+Return": "spawn foot"}
    assert data["general"] == {"xwayland": True}
    assert data["include"]["files"] == []


def test_no_packaged_config_is_an_error_and_writes_nothing(cfg, no_packaged):
    with pytest.raises(UmbrielConfigError):
        ensure_umbriel_include()

    assert not (cfg / "config.toml").exists()


def test_custom_config_dir_without_config_is_left_alone(
    cfg, packaged, monkeypatch, tmp_path,
):
    monkeypatch.setattr(utils, "_runtime_config_dir", str(tmp_path / "custom"))

    assert ensure_umbriel_include() is False
    assert not (tmp_path / "custom" / "config.toml").exists()
    assert not (cfg / "config.toml").exists()


def test_error_is_a_runtime_error():
    assert issubclass(UmbrielConfigError, RuntimeError)


# ── adding the include ───────────────────────────────────────────────────

def test_include_is_appended_when_there_is_no_include_table(cfg):
    path = _write(cfg, '[general]\nxwayland = false\n')

    assert ensure_umbriel_include() is True

    data = _load(path)
    assert data["general"] == {"xwayland": False}
    assert data["include"]["optional"]["files"] == ["monitors.toml"]
    text = path.read_text(encoding="utf-8")
    assert text.count(MARKER_PREFIX) == 1
    marker, files = text.splitlines()[-2:]
    assert marker == MARKER_PREFIX + "monitors.toml"
    assert files.startswith("files")


@pytest.mark.parametrize("files_line,expected", [
    ("", ["monitors.toml"]),
    ("files = []\n", ["monitors.toml"]),
    ('files = ["a.toml"]\n', ["a.toml", "monitors.toml"]),
    ('files = ["a.toml",]  # mine\n', ["a.toml", "monitors.toml"]),
])
def test_existing_optional_include_gets_the_file_last(cfg, files_line, expected):
    path = _write(cfg, f"[include.optional]\n{files_line}\n[general]\nx = 1\n")

    assert ensure_umbriel_include() is True

    data = _load(path)
    assert data["include"]["optional"]["files"] == expected
    assert data["general"] == {"x": 1}


def test_plain_include_table_is_kept(cfg):
    path = _write(cfg, '[include]\nfiles = ["base.toml"]\n')

    ensure_umbriel_include()

    data = _load(path)
    assert data["include"]["files"] == ["base.toml"]
    assert data["include"]["optional"]["files"] == ["monitors.toml"]


@pytest.mark.parametrize("body", [
    '[include]\nfiles = ["monitors.toml"]\n',
    '[include.optional]\nfiles = ["x.toml", "monitors.toml"]\n',
])
def test_users_own_include_is_respected(cfg, body):
    path = _write(cfg, body + "[output.DP-1]\nmode = \"1x1\"\n")
    before = path.read_bytes()

    assert ensure_umbriel_include() is False

    assert path.read_bytes() == before


def test_second_run_is_a_no_op(cfg):
    path = _write(cfg, "[general]\nx = 1\n")
    ensure_umbriel_include()
    before = path.read_bytes()

    assert ensure_umbriel_include() is False

    assert path.read_bytes() == before


def test_previous_file_is_backed_up(cfg):
    path = _write(cfg, "[general]\nx = 1\n")

    ensure_umbriel_include()

    assert (cfg / "config.toml.bak").read_text() == "[general]\nx = 1\n"
    assert path.read_text() != "[general]\nx = 1\n"


# ── rename ───────────────────────────────────────────────────────────────

def test_rename_swaps_the_managed_entry(cfg):
    path = _write(cfg, '[include.optional]\nfiles = ["a.toml"]\n')
    ensure_umbriel_include()
    utils.save_app_settings({"monitor_config_name": "display"})

    assert ensure_umbriel_include() is True

    data = _load(path)
    assert data["include"]["optional"]["files"] == ["a.toml", "display.toml"]
    text = path.read_text(encoding="utf-8")
    assert text.count(MARKER_PREFIX) == 1
    assert MARKER_PREFIX + "display.toml" in text
    assert "monitors.toml" not in text


# ── managed output keys ──────────────────────────────────────────────────

OUTPUTS = """\
[output.DP-1]
enabled = true
mode = "2560x1440@144"
position = [0, 0]
scale = 1.25
transform = "90"
vrr = "always"
hdr = "on"
bit_depth = 10
focus_at_startup = true
workspaces = 3  # kept
tearing = true

[output."HDMI A 1"]
mode = "1x1"

[output.DP-2.layout.scrolling]
default_extent_fraction = 0.4
"""


def test_first_run_strips_only_the_keys_monique_manages(cfg):
    path = _write(cfg, OUTPUTS + '\n[general]\nmode = "keep"\n')

    ensure_umbriel_include()

    data = _load(path)
    assert data["output"]["DP-1"] == {"workspaces": 3, "tearing": True}
    assert data["output"]["HDMI A 1"] == {}
    assert data["output"]["DP-2"]["layout"]["scrolling"] == {
        "default_extent_fraction": 0.4}
    assert data["general"] == {"mode": "keep"}
    assert "# kept" in path.read_text(encoding="utf-8")


def test_later_runs_never_touch_output_tables(cfg):
    path = _write(cfg, "[general]\nx = 1\n")
    ensure_umbriel_include()
    path.write_text(path.read_text() + '\n[output.DP-1]\nmode = "1x1"\n')
    before = path.read_bytes()

    assert ensure_umbriel_include() is False
    utils.save_app_settings({"monitor_config_name": "other"})
    ensure_umbriel_include()

    assert _load(path)["output"]["DP-1"] == {"mode": "1x1"}
    assert before != path.read_bytes()  # il rename ha agito, non sulle tabelle


# ── unverifiable layouts ─────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    'output.DP-1.mode = "1x1"\n',
    'include = { files = ["a.toml"] }\n',
    '[include.optional]\nfiles = [\n  "a.toml",\n]\n',
    "[output\nbroken",
])
def test_unverifiable_layout_fails_and_leaves_the_file_alone(cfg, text):
    path = _write(cfg, text)

    with pytest.raises(UmbrielConfigError):
        ensure_umbriel_include()

    assert path.read_text(encoding="utf-8") == text
    assert not (cfg / "config.toml.bak").exists()


# ── revert ───────────────────────────────────────────────────────────────

def test_umbriel_primary_declares_config_toml_and_revert_restores_it(cfg):
    original = OUTPUTS
    path = _write(cfg, original)
    paths = compositor_config_paths(UMBRIEL)

    assert paths[0] == cfg / "monitors.toml"
    assert path in paths
    for p in paths:
        utils.backup_file(p)
    ensure_umbriel_include()
    assert path.read_text() != original

    assert utils.restore_backup(path) is True

    assert path.read_text() == original


# ── integrazione con il vero parser di Umbriel ───────────────────────────

@pytest.mark.skipif(shutil.which("umbriel") is None,
                    reason="umbriel is not on PATH")
def test_edited_config_validates_with_real_umbriel(cfg):
    path = _write(cfg, PACKAGED + "\n" + OUTPUTS)
    ensure_umbriel_include()

    done = subprocess.run(
        ["umbriel", "config", "validate", "--json", "-c", str(path)],
        capture_output=True, text=True, timeout=30,
    )

    report = json.loads(done.stdout)
    assert report["valid"] is True, report["diagnostics"]
