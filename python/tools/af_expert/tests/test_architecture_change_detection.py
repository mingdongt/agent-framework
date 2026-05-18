from __future__ import annotations

from pathlib import Path

import pytest

from af_expert.architecture.change_detection import (
    detect_architectural_drift,
    extract_changed_paths_from_diff,
)


def test_extract_paths_from_unified_diff() -> None:
    diff = (
        "diff --git a/src/foo/chat_client.py b/src/foo/chat_client.py\n"
        "index 1234..5678 100644\n"
        "--- a/src/foo/chat_client.py\n"
        "+++ b/src/foo/chat_client.py\n"
        "@@ -10,3 +10,4 @@\n"
        " class X:\n"
        "+    pass\n"
        "diff --git a/tests/test_foo.py b/tests/test_foo.py\n"
        "index abcd..efgh 100644\n"
        "--- a/tests/test_foo.py\n"
        "+++ b/tests/test_foo.py\n"
    )
    paths = extract_changed_paths_from_diff(diff)
    assert "src/foo/chat_client.py" in paths
    assert "tests/test_foo.py" in paths


def test_extract_paths_handles_empty_diff() -> None:
    assert extract_changed_paths_from_diff("") == set()
    assert extract_changed_paths_from_diff(None) == set()


def test_detect_drift_when_core_file_touched(tmp_path: Path) -> None:
    core_paths = ["src/foo/chat_client.py", "src/foo/agent.py"]
    prs = [
        {
            "number": 100,
            "diff": (
                "diff --git a/src/foo/chat_client.py b/src/foo/chat_client.py\n"
                "+++ b/src/foo/chat_client.py\n"
            ),
        }
    ]
    drift = detect_architectural_drift(core_paths=core_paths, prs=prs)
    assert drift.has_drift is True
    assert "src/foo/chat_client.py" in drift.touched_core_paths


def test_detect_drift_returns_false_for_unrelated_changes() -> None:
    core_paths = ["src/foo/chat_client.py"]
    prs = [
        {"number": 1, "diff": "diff --git a/docs/x.md b/docs/x.md\n+++ b/docs/x.md\n"},
        {"number": 2, "diff": None},
    ]
    drift = detect_architectural_drift(core_paths=core_paths, prs=prs)
    assert drift.has_drift is False
