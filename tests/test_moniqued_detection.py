"""Rilevamento di moniqued, usato per l'avviso kanshi in Preferences."""

from __future__ import annotations

import os
from pathlib import Path

from monique.utils import is_moniqued_running


def _add_process(proc: Path, pid: int, *argv: str) -> None:
    d = proc / str(pid)
    d.mkdir()
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")


def test_detects_python_script(tmp_path: Path) -> None:
    _add_process(tmp_path, 10, "/usr/bin/python", "/usr/bin/moniqued")
    assert is_moniqued_running(tmp_path)


def test_detects_python_with_flags(tmp_path: Path) -> None:
    _add_process(tmp_path, 10, "python3.14", "-I", "/home/u/.venv/bin/moniqued")
    assert is_moniqued_running(tmp_path)


def test_detects_direct_executable(tmp_path: Path) -> None:
    _add_process(tmp_path, 10, "moniqued")
    assert is_moniqued_running(tmp_path)


def test_detects_nix_wrapper(tmp_path: Path) -> None:
    _add_process(tmp_path, 10, "/nix/store/abc/bin/.moniqued-wrapped")
    assert is_moniqued_running(tmp_path)


def test_ignores_other_processes(tmp_path: Path) -> None:
    _add_process(tmp_path, 10, "/usr/bin/python", "/usr/bin/monique")
    _add_process(tmp_path, 11, "vim", "/usr/bin/moniqued")
    _add_process(tmp_path, 12, "systemctl", "--user", "stop", "moniqued")
    _add_process(tmp_path, 13, "/usr/bin/python", "/tmp/script.py", "moniqued")
    assert not is_moniqued_running(tmp_path)


def test_ignores_other_users(tmp_path: Path, monkeypatch) -> None:
    _add_process(tmp_path, 10, "/usr/bin/python", "/usr/bin/moniqued")
    monkeypatch.setattr(os, "getuid", lambda: os.stat(tmp_path).st_uid + 1)
    assert not is_moniqued_running(tmp_path)


def test_ignores_unreadable_entries(tmp_path: Path) -> None:
    (tmp_path / "self").mkdir()
    (tmp_path / "20").mkdir()  # processo terminato: niente cmdline
    (tmp_path / "21").mkdir()
    (tmp_path / "21" / "cmdline").write_bytes(b"")  # kernel thread
    assert not is_moniqued_running(tmp_path)


def test_missing_proc_means_not_running(tmp_path: Path) -> None:
    assert not is_moniqued_running(tmp_path / "missing")
