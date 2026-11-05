"""Client IPC di Umbriel: protocollo a una riga JSON, apply e flusso eventi."""

import asyncio
import copy
import json
import shutil
import socket
import tempfile
import threading
import tomllib
from pathlib import Path

import pytest

from monique.models import MonitorConfig, PositionMode, Profile
from monique.umbriel import UmbrielIPC

FIXTURE = Path(__file__).parent / "fixtures" / "umbriel_outputs.json"


def _outputs() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def sockdir():
    # i path dei socket unix stanno sotto i 108 byte: tmp_path puo' superarli
    path = Path(tempfile.mkdtemp(prefix="umb"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _ipc(path) -> UmbrielIPC:
    ipc = UmbrielIPC()
    ipc._socket_path = str(path)
    return ipc


class _Server:
    """One-shot sync server: answers each connection with *chunks*, then idles."""

    def __init__(self, path, chunks):
        self.requests: list[bytes] = []
        self._chunks = chunks
        self._sock = socket.socket(socket.AF_UNIX)
        self._sock.bind(str(path))
        self._sock.listen(1)
        self._release = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        conn, _ = self._sock.accept()
        with conn:
            buf = b""
            while not buf.endswith(b"\n"):
                buf += conn.recv(4096)
            self.requests.append(buf)
            for chunk in self._chunks:
                conn.sendall(chunk)
            # non chiude: il client non deve aspettare l'EOF
            self._release.wait(5)

    def close(self):
        self._release.set()
        self._thread.join(5)
        self._sock.close()


@pytest.fixture
def serve(sockdir):
    servers: list[_Server] = []

    def start(*chunks: bytes) -> UmbrielIPC:
        path = sockdir / f"s{len(servers)}.sock"
        servers.append(_Server(path, chunks))
        return _ipc(path)

    start.servers = servers
    yield start
    for server in servers:
        server.close()


# ── _request ─────────────────────────────────────────────────────────────

def test_request_returns_the_ok_value_without_waiting_for_eof(serve):
    ipc = serve(b'{"ok":[1,2]}\n')

    assert ipc._request({"cmd": "x"}) == [1, 2]


def test_request_tolerates_fragmented_replies(serve):
    ipc = serve(b'{"ok":', b'{"a":', b'1}}', b"\n")

    assert ipc._request({"cmd": "x"}) == {"a": 1}


def test_request_sends_one_json_line(serve):
    ipc = serve(b'{"ok":null}\n')

    ipc._request({"cmd": "outputs"})
    serve.servers[0].close()

    request = serve.servers[0].requests[0]
    assert request.endswith(b"\n") and request.count(b"\n") == 1
    assert json.loads(request) == {"cmd": "outputs"}


def test_err_reply_raises_runtime_error(serve):
    ipc = serve(b'{"err":"unknown command: bogus"}\n')

    with pytest.raises(RuntimeError, match="unknown command: bogus"):
        ipc._request({"cmd": "bogus"})


def test_closed_without_reply_raises(sockdir):
    path = sockdir / "c.sock"
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(path))
    server.listen(1)

    def accept_and_close():
        conn, _ = server.accept()
        conn.close()

    thread = threading.Thread(target=accept_and_close, daemon=True)
    thread.start()

    with pytest.raises(ConnectionError):
        _ipc(path)._request({"cmd": "x"})
    thread.join(5)
    server.close()


# ── queries ──────────────────────────────────────────────────────────────

def test_get_monitors_parses_the_real_capture(monkeypatch):
    ipc = UmbrielIPC()
    monkeypatch.setattr(ipc, "_request", lambda cmd: _outputs())

    monitors = ipc.get_monitors()

    assert [m.name for m in monitors] == ["HEADLESS-1", "V2"]
    assert monitors[1].refresh_rate == 30.0


def test_get_workspaces_uses_the_workspaces_command(monkeypatch):
    ipc = UmbrielIPC()
    seen = []
    monkeypatch.setattr(ipc, "_request", lambda cmd: seen.append(cmd) or [])

    assert ipc.get_workspaces() == []
    assert seen == [{"cmd": "workspaces"}]


def test_reload_is_a_no_op():
    assert UmbrielIPC().reload() is None


def test_there_is_no_workspace_migration():
    # Umbriel sposta da solo i workspace: nessun move_workspace_to_monitor
    assert not hasattr(UmbrielIPC, "move_workspace_to_monitor")


# ── apply_profile ────────────────────────────────────────────────────────

@pytest.fixture
def applying(isolated_config, monkeypatch):
    """An IPC whose requests are recorded; nothing else is installed."""
    for name in ("hyprland", "sway", "niri"):
        for module in ("umbriel", "config_paths"):
            monkeypatch.setattr(f"monique.{module}.is_{name}_installed", lambda: False)
    for name in ("is_sddm_running", "is_greetd_running"):
        monkeypatch.setattr(f"monique.umbriel.{name}", lambda: False)
    (isolated_config / "umbriel").mkdir()
    (isolated_config / "umbriel" / "config.toml").write_text("[general]\nx = 1\n")

    ipc = UmbrielIPC()
    state = {"outputs": _outputs(), "sent": []}

    def request(cmd):
        if cmd["cmd"] == "outputs":
            if state["outputs"] is None:
                raise OSError("down")
            return state["outputs"]
        state["sent"].append(cmd)
        return None

    monkeypatch.setattr(ipc, "_request", request)
    return ipc, state, isolated_config / "umbriel"


def _twin(name: str) -> dict:
    out = copy.deepcopy(_outputs()[1])
    out.update(name=name, make="AOC", model="m", serial="", enabled=True,
               config_name="AOC m")
    return out


def _profile(*monitors: MonitorConfig) -> Profile:
    return Profile(name="p", monitors=list(monitors))


def test_apply_writes_monitors_and_includes_it(applying):
    ipc, _, cfg = applying
    mon = MonitorConfig(name="V2", width=800, height=600, refresh_rate=30.0,
                        x=1280, position_mode=PositionMode.EXPLICIT)

    ipc.apply_profile(_profile(mon), use_description=False)

    tables = tomllib.loads((cfg / "monitors.toml").read_text())["output"]
    assert tables["V2"]["position"] == [1280, 0]
    config = tomllib.loads((cfg / "config.toml").read_text())
    assert config["include"]["optional"]["files"] == ["monitors.toml"]


def test_apply_uses_the_live_config_name(applying):
    ipc, state, cfg = applying
    state["outputs"][1].update(make="AOC", model="2757", serial="1",
                               config_name="PNP(AOC) 2757 1")
    mon = MonitorConfig(name="DP-9", description="AOC 2757 1", make="AOC",
                        model="2757", serial="1")

    ipc.apply_profile(_profile(mon), use_description=True)

    assert list(tomllib.loads((cfg / "monitors.toml").read_text())["output"]) == [
        "PNP(AOC) 2757 1"]


def test_apply_survives_an_ipc_failure(applying):
    ipc, state, cfg = applying
    state["outputs"] = None
    mon = MonitorConfig(name="DP-9", description="AOC 2757 1", make="AOC",
                        model="2757", serial="1")

    ipc.apply_profile(_profile(mon), use_description=True)

    assert list(tomllib.loads((cfg / "monitors.toml").read_text())["output"]) == [
        "PNP(AOC) 2757 1"]


def test_power_is_synced_only_where_live_state_disagrees(applying):
    ipc, state, _ = applying
    off = MonitorConfig(name="V2", enabled=False)
    same = MonitorConfig(name="HEADLESS-1", enabled=True)

    ipc.apply_profile(_profile(off, same), use_description=False)

    assert state["sent"] == [
        {"cmd": "action", "action": "output-disable", "output": "V2"}]


def test_power_sync_enables_a_disabled_output(applying):
    ipc, state, _ = applying
    state["outputs"][1]["enabled"] = False

    ipc.apply_profile(_profile(MonitorConfig(name="V2")), use_description=False)

    assert state["sent"] == [
        {"cmd": "action", "action": "output-enable", "output": "V2"}]


def test_power_sync_targets_the_right_twin(applying):
    ipc, state, _ = applying
    state["outputs"] = [
        _twin("DP-1"), _twin("DP-2"),
    ]
    off = MonitorConfig(name="DP-1", description="AOC m", enabled=False)
    on = MonitorConfig(name="DP-2", description="AOC m", enabled=True)

    ipc.apply_profile(_profile(off, on), use_description=True)

    assert state["sent"] == [
        {"cmd": "action", "action": "output-disable", "output": "DP-1"}]


def test_power_sync_skips_ambiguous_twins(applying):
    ipc, state, _ = applying
    state["outputs"] = [_twin("DP-1"), _twin("DP-2")]
    # nessun connettore del profilo coincide con quelli vivi
    off = MonitorConfig(name="DP-7", description="AOC m", enabled=False)

    ipc.apply_profile(_profile(off), use_description=True)

    assert state["sent"] == []


def test_unverifiable_config_toml_fails_the_apply(applying):
    ipc, _, cfg = applying
    (cfg / "config.toml").write_text('output.DP-1.mode = "1x1"\n')

    with pytest.raises(RuntimeError):
        ipc.apply_profile(_profile(MonitorConfig(name="V2")), use_description=False)


def test_config_paths_declare_what_apply_writes(applying):
    ipc, _, cfg = applying

    assert ipc.config_paths() == [cfg / "monitors.toml", cfg / "config.toml"]


# ── event stream ─────────────────────────────────────────────────────────

def _snapshot(outputs: list[dict]) -> bytes:
    return (json.dumps({"event": "outputs", "data": outputs}) + "\n").encode()


def _out(name, serial="1", **extra) -> dict:
    out = copy.deepcopy(_outputs()[1])
    out.update(name=name, make="AOC", model="m", serial=serial, **extra)
    return out


async def _collect(sockdir, lines: list[bytes]) -> list[dict]:
    """Serve *lines* after the subscribe request and gather the yielded events."""
    path = sockdir / "ev.sock"
    requests: list[bytes] = []

    async def handler(reader, writer):
        requests.append(await reader.readline())
        for line in lines:
            writer.write(line)
            await writer.drain()
        writer.close()

    server = await asyncio.start_unix_server(handler, path=str(path))
    events = []
    try:
        async for event in _ipc(path).connect_event_socket():
            events.append(event)
    finally:
        server.close()
        await server.wait_closed()
    assert json.loads(requests[0]) == {"cmd": "subscribe", "events": ["outputs"]}
    return events


def test_first_snapshot_is_recorded_not_yielded(sockdir):
    events = asyncio.run(_collect(sockdir, [_snapshot([_out("DP-1")])]))

    assert events == []


def test_snapshots_with_the_same_outputs_are_ignored(sockdir):
    # posizione, workspace attivo, focus: cambiano senza hotplug
    lines = [
        _snapshot([_out("DP-1")]),
        _snapshot([_out("DP-1", focused=True)]),
        _snapshot([_out("DP-1", position={"x": 5, "y": 5})]),
    ]

    assert asyncio.run(_collect(sockdir, lines)) == []


def test_added_and_removed_outputs_are_yielded_once_each(sockdir):
    lines = [
        _snapshot([_out("DP-1")]),
        _snapshot([_out("DP-1"), _out("DP-2", serial="2")]),
        _snapshot([_out("DP-1"), _out("DP-2", serial="2", focused=True)]),
        _snapshot([_out("DP-1")]),
    ]

    events = asyncio.run(_collect(sockdir, lines))

    assert len(events) == 2


def test_different_monitor_on_the_same_connector_counts(sockdir):
    lines = [_snapshot([_out("DP-1", serial="1")]),
             _snapshot([_out("DP-1", serial="2")])]

    assert len(asyncio.run(_collect(sockdir, lines))) == 1


def test_a_very_long_snapshot_line_is_read(sockdir):
    big = _out("DP-1")
    big["modes"] = big["modes"] * 4000
    line = _snapshot([big])
    assert len(line) > 1 << 17

    events = asyncio.run(_collect(sockdir, [line, _snapshot([big, _out("DP-2", serial="2")])]))

    assert len(events) == 1


def test_garbage_and_blank_lines_are_skipped(sockdir):
    lines = [b"\n", b"not json\n", b"[1]\n", _snapshot([_out("DP-1")]),
             _snapshot([])]

    assert len(asyncio.run(_collect(sockdir, lines))) == 1


def test_err_reply_to_subscribe_raises(sockdir):
    with pytest.raises(RuntimeError, match="nope"):
        asyncio.run(_collect(sockdir, [b'{"err":"nope"}\n']))
