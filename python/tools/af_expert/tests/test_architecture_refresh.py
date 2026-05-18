from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from af_expert.architecture.refresh import (
    RefreshResult,
    refresh_one_repo,
    repo_briefing_path,
)
from af_expert.architecture.scanner import FileInventory
from af_expert.llm import LLM, LLMResponse


def test_repo_briefing_path_encodes_owner(tmp_state_dir: Path) -> None:
    p = repo_briefing_path("microsoft/agent-framework")
    assert p.name == "architecture.md"
    assert p.parent.name == "microsoft__agent-framework"


def test_refresh_writes_briefing_to_disk(tmp_state_dir: Path, tmp_path: Path) -> None:
    fake_inventory = FileInventory(repo_root=tmp_path / "fake")
    fake_inventory.source_files = ["src/x.py"]
    fake_inventory.readme_excerpt = "Fake repo"

    llm = MagicMock(spec=LLM)
    llm.complete.return_value = LLMResponse(
        text="## Purpose\nA fake.\n",
        input_tokens=50, output_tokens=10, cache_read_tokens=0, cache_creation_tokens=0,
    )

    with patch("af_expert.architecture.refresh._clone_repo_shallow") as fake_clone, \
         patch("af_expert.architecture.refresh.scan_repo_locally") as fake_scan:
        fake_clone.return_value = tmp_path / "fake-clone"
        fake_scan.return_value = fake_inventory

        result = refresh_one_repo("microsoft/agent-framework", llm=llm)

    assert isinstance(result, RefreshResult)
    assert result.repo == "microsoft/agent-framework"
    assert result.success is True
    assert "A fake" in result.briefing_path.read_text(encoding="utf-8")


def test_refresh_returns_failure_on_clone_error(tmp_state_dir: Path) -> None:
    llm = MagicMock(spec=LLM)
    with patch("af_expert.architecture.refresh._clone_repo_shallow") as fake_clone:
        fake_clone.side_effect = RuntimeError("git clone failed")

        result = refresh_one_repo("microsoft/agent-framework", llm=llm)

    assert result.success is False
    assert "clone failed" in (result.error or "").lower()
    assert result.briefing_path.exists() or result.error is not None
