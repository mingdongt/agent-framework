# Copyright (c) Microsoft. All rights reserved.

"""End-to-end smoke tests. Real LLM, real GitHub, real Docker. NEVER runs in CI.

Run manually:
    cd python/tools/af_fix
    uv run pytest tests/e2e -m e2e -v

Requires ~/.af-fix/config.toml + Docker running + ANTHROPIC_API_KEY.
"""

import pytest

from af_fix.cli import main


@pytest.mark.e2e
def test_triage_only() -> None:
    assert main(["--top", "3", "--triage-only"]) == 0


@pytest.mark.e2e
def test_no_push_full_run() -> None:
    assert main(["--top", "1", "--no-push"]) == 0
