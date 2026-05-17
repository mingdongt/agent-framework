from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from af_expert.state import (
    StateDir,
    StateLockError,
    atomic_write,
    load_state,
    save_state,
)


def test_state_dir_layout(tmp_state_dir: Path) -> None:
    sd = StateDir()
    sd.ensure_layout()

    assert (tmp_state_dir / "repos").is_dir()
    assert (tmp_state_dir / "candidates").is_dir()
    assert (tmp_state_dir / "digests").is_dir()


def test_atomic_write_roundtrip(tmp_state_dir: Path) -> None:
    target = tmp_state_dir / "foo.json"
    atomic_write(target, '{"a": 1}')
    assert target.read_text() == '{"a": 1}'


def test_atomic_write_overwrites(tmp_state_dir: Path) -> None:
    target = tmp_state_dir / "foo.json"
    atomic_write(target, "v1")
    atomic_write(target, "v2")
    assert target.read_text() == "v2"


def test_atomic_write_no_partial_on_failure(tmp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_state_dir / "foo.json"
    target.write_text("original")

    import af_expert.state as state_mod

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated rename failure")

    monkeypatch.setattr(state_mod.os, "replace", boom)

    with pytest.raises(RuntimeError):
        atomic_write(target, "new")

    assert target.read_text() == "original"


def test_load_state_missing_returns_empty(tmp_state_dir: Path) -> None:
    state = load_state()
    assert state == {"version": 1, "cursors": {}, "stats": {}}


def test_save_and_load_state(tmp_state_dir: Path) -> None:
    save_state({"version": 1, "cursors": {"microsoft/agent-framework": "2026-05-17T00:00:00Z"}, "stats": {}})
    state = load_state()
    assert state["cursors"]["microsoft/agent-framework"] == "2026-05-17T00:00:00Z"


def test_lock_prevents_concurrent_run(tmp_state_dir: Path) -> None:
    sd = StateDir()
    sd.ensure_layout()

    with sd.lock():
        with pytest.raises(StateLockError):
            with sd.lock():
                pass


def test_lock_releases_on_exit(tmp_state_dir: Path) -> None:
    sd = StateDir()
    sd.ensure_layout()

    with sd.lock():
        pass

    with sd.lock():
        pass  # second acquisition should now succeed
