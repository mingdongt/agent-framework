from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect AF_EXPERT_STATE_DIR to a tmp dir for the duration of a test."""
    state_dir = tmp_path / "af-expert"
    state_dir.mkdir()
    monkeypatch.setenv("AF_EXPERT_STATE_DIR", str(state_dir))
    yield state_dir
