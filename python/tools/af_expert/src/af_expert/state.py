from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from af_expert.config import _state_dir


class StateLockError(RuntimeError):
    pass


def atomic_write(target: Path, content: str) -> None:
    """Atomic write: write to tmp file, then os.replace into target."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    try:
        os.replace(tmp, target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


class StateDir:
    def __init__(self) -> None:
        self.root = _state_dir()

    def ensure_layout(self) -> None:
        for sub in ("repos", "candidates", "digests"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    @property
    def lock_path(self) -> Path:
        return self.root / "lock"

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError as e:
            existing = self.lock_path.read_text(errors="ignore").strip()
            raise StateLockError(
                f"Lock held (pid {existing}) at {self.lock_path}. "
                f"If no af-expert process is running, remove this file."
            ) from e
        try:
            yield
        finally:
            self.lock_path.unlink(missing_ok=True)


def load_state() -> dict[str, Any]:
    sd = StateDir()
    if not sd.state_path.exists():
        return {"version": 1, "cursors": {}, "stats": {}}
    return json.loads(sd.state_path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    sd = StateDir()
    sd.ensure_layout()
    atomic_write(sd.state_path, json.dumps(state, indent=2, sort_keys=True))
