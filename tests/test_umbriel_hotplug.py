"""Hotplug Umbriel end to end: demone reale, UmbrielIPC reale, server finto."""

from __future__ import annotations

import asyncio
import copy
import json
import shutil
import tempfile
import threading
from pathlib import Path

import pytest

from monique import daemon as daemon_mod
from monique.daemon import MonitorDaemon
from monique.models import MonitorConfig, Profile
from monique.profile_manager import ProfileManager
from monique.umbriel import UmbrielIPC

FIXTURE = Path(__file__).parent / "fixtures" / "umbriel_outputs.json"
DEBOUNCE_MS = 50
TIMEOUT_S = 10.0


def _out(name: str, serial: str, **extra) -> dict:
    out = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8"))[1])
    out.update(
        name=name, make="AOC", model="m", serial=serial, enabled=True,
        config_name=f"PNP(AOC) m {serial}", **extra,
    )
    return out


class _FakeUmbrielServer:
    """Umbriel finto su un thread con un loop proprio.

    Il client di richieste e' sincrono e blocca l'event loop del demone: il
    server non puo' girare sullo stesso loop.
    """

    def __init__(self, path: str, outputs: list[dict]) -> None:
        self.outputs = outputs
        self.subscribers: list[asyncio.StreamWriter] = []
        self.requests: list[dict] = []
        self._path = path
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._ready.wait(TIMEOUT_S)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        server = self._loop.run_until_complete(
            asyncio.start_unix_server(self._handle, path=self._path))
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            # niente wait_closed(): attenderebbe i client ancora connessi
            server.close()
            self._loop.close()

    @staticmethod
    def _event(outputs: list[dict]) -> bytes:
        return (json.dumps({"event": "outputs", "data": outputs}) + "\n").encode()

    async def _handle(self, reader, writer) -> None:
        request = json.loads(await reader.readline())
        self.requests.append(request)
        cmd = request.get("cmd")
        if cmd == "subscribe":
            writer.write(self._event(self.outputs))
            await writer.drain()
            self.subscribers.append(writer)
            await reader.read()  # fino alla chiusura del client
            return
        reply = {"ok": {"outputs": self.outputs, "workspaces": []}.get(cmd)}
        writer.write((json.dumps(reply) + "\n").encode())
        await writer.drain()
        writer.close()

    def push(self, outputs: list[dict]) -> None:
        """Send a snapshot to every subscriber, as Umbriel does on a change."""
        async def send() -> None:
            self.outputs = outputs
            for writer in self.subscribers:
                writer.write(self._event(outputs))
                await writer.drain()

        asyncio.run_coroutine_threadsafe(send(), self._loop).result(TIMEOUT_S)

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(TIMEOUT_S)


@pytest.fixture
def fake_umbriel():
    # i path dei socket unix stanno sotto i 108 byte: tmp_path puo' superarli
    sockdir = Path(tempfile.mkdtemp(prefix="umb"))
    server = _FakeUmbrielServer(str(sockdir / "u.sock"), [_out("DP-1", "1")])
    yield server, sockdir / "u.sock"
    server.stop()
    shutil.rmtree(sockdir, ignore_errors=True)


@pytest.fixture
def isolated_umbriel(isolated_config, monkeypatch):
    for name in ("hyprland", "sway", "niri"):
        for module in ("umbriel", "config_paths"):
            monkeypatch.setattr(f"monique.{module}.is_{name}_installed", lambda: False)
    for name in ("is_sddm_running", "is_greetd_running"):
        monkeypatch.setattr(f"monique.umbriel.{name}", lambda: False)
    monkeypatch.setattr(daemon_mod, "DEBOUNCE_MS", DEBOUNCE_MS)
    cfg = isolated_config / "umbriel"
    cfg.mkdir()
    (cfg / "config.toml").write_text("[general]\nx = 1\n")
    return cfg


def _mon(name: str, serial: str) -> MonitorConfig:
    return MonitorConfig(
        name=name, description=f"AOC m {serial}", make="AOC", model="m",
        serial=serial,
    )


async def _until(condition, what: str) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(poll(), TIMEOUT_S)
    except asyncio.TimeoutError:
        pytest.fail(f"timed out waiting for {what}")


async def _quiet() -> None:
    """Let several debounce windows pass."""
    await asyncio.sleep(DEBOUNCE_MS * 6 / 1000)


def test_hotplug_applies_only_for_a_new_identity(
    fake_umbriel, isolated_umbriel, monkeypatch,
) -> None:
    server, path = fake_umbriel
    mgr = ProfileManager()
    mgr.save(Profile(name="One", monitors=[_mon("DP-1", "1")]))
    mgr.save(Profile(name="Two", monitors=[_mon("DP-1", "1"), _mon("DP-2", "2")]))

    applied: list[str] = []
    real_apply = UmbrielIPC.apply_profile

    def counting(self, profile, **kwargs):
        applied.append(profile.name)
        return real_apply(self, profile, **kwargs)

    monkeypatch.setattr(UmbrielIPC, "apply_profile", counting)
    ipc = UmbrielIPC()
    ipc._socket_path = str(path)
    monitors_toml = isolated_umbriel / "monitors.toml"

    async def scenario() -> None:
        task = asyncio.ensure_future(MonitorDaemon()._listen(ipc))
        try:
            await _until(lambda: server.subscribers, "the subscription")
            # apply iniziale forzato
            assert applied == ["One"]
            assert 'PNP(AOC) m 1' in monitors_toml.read_text()

            # solo focus e layout: nessun apply
            one = _out("DP-1", "1")
            server.push([{**one, "focused": True}])
            server.push([{**one, "position": {"x": 7, "y": 7}}])
            await _quiet()
            assert applied == ["One"]

            # una nuova identita': esattamente un apply
            both = [one, _out("DP-2", "2")]
            server.push(both)
            await _until(lambda: len(applied) == 2, "the hotplug apply")
            assert applied == ["One", "Two"]
            assert 'PNP(AOC) m 2' in monitors_toml.read_text()

            # gli eco dell'apply (stesse identita') non innescano nulla
            server.push([{**both[0], "focused": True}, both[1]])
            server.push(both)
            await _quiet()
            assert applied == ["One", "Two"]
            assert not task.done()
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(asyncio.wait_for(scenario(), TIMEOUT_S * 3))
