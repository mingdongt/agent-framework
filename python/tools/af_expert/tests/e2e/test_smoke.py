from __future__ import annotations

import os
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

from af_expert.cli import cli
from click.testing import CliRunner


@pytest.mark.e2e
def test_e2e_tick_produces_at_least_ingestion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run a real tick against 2 small real repos. Verifies ingestion + S1 loop end-to-end."""
    if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("GITHUB_TOKEN"):
        pytest.skip("Set ANTHROPIC_API_KEY and GITHUB_TOKEN to run e2e smoke")

    state_dir = tmp_path / "af-expert"
    state_dir.mkdir()
    monkeypatch.setenv("AF_EXPERT_STATE_DIR", str(state_dir))

    cfg = state_dir / "config.toml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            github_token = "{os.environ['GITHUB_TOKEN']}"
            anthropic_api_key = "{os.environ['ANTHROPIC_API_KEY']}"

            [[repos]]
            owner_repo = "microsoft/agent-framework"
            priority = "high"
            languages = ["python"]

            [[repos]]
            owner_repo = "pydantic/pydantic-ai"
            priority = "normal"
            languages = ["python"]
            """
        ).strip()
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["tick"])
    assert result.exit_code == 0, result.output
    # Ingestion should have happened
    assert "Ingestion:" in result.output
