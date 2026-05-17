# Copyright (c) Microsoft. All rights reserved.
"""End-to-end smoke test. Requires `claude` CLI on PATH and GITHUB_TOKEN env."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _have_prereqs() -> bool:
    return shutil.which("claude") is not None and bool(os.environ.get("GITHUB_TOKEN"))


@pytest.mark.skipif(not _have_prereqs(), reason="needs `claude` on PATH and GITHUB_TOKEN")
def test_smoke_minimal_pipeline(tmp_path: Path) -> None:
    """Init + run with --window 1d against one repo. Asserts briefing.md non-empty."""
    home = tmp_path / "af-watch"
    env = {
        **os.environ,
        "AF_WATCH_HOME": str(home),
    }
    # init
    subprocess.run(
        ["uv", "run", "af-watch", "init"],
        env=env, capture_output=True, text=True, check=True,
    )
    assert (home / "config.toml").exists()

    # Write a minimal real config (no API key — claude CLI carries auth)
    (home / "config.toml").write_text(f'''
github_token = "{os.environ["GITHUB_TOKEN"]}"
operator_name = "smoke"
home_repo = "microsoft/agent-framework"
target_repos = ["microsoft/agent-framework"]
industry_sources = []
max_regions_per_run = 2
reasoning_model = "haiku"
''', encoding="utf-8")

    # run (1 day window, skip repro)
    r = subprocess.run(
        ["uv", "run", "af-watch", "run", "--window", "1d", "--skip-repro"],
        env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"

    reports = list((home / "reports").glob("*/briefing.md"))
    assert reports, f"no briefing produced. stderr={r.stderr}"
    content = reports[0].read_text(encoding="utf-8")
    assert "Weekly Briefing" in content
