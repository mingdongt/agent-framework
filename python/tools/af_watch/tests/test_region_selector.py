# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timezone

from af_watch.models import ActivityEvent
from af_watch.region_selector import RegionSelector


def _event(repo: str, files: list[str], type_: str = "pr_merged", number: int = 1) -> ActivityEvent:
    return ActivityEvent(
        repo=repo,
        type=type_,  # type: ignore[arg-type]
        number=number,
        title="fix: x",
        timestamp=datetime(2026, 5, 17, tzinfo=timezone.utc),
        files_changed=files,
        url=f"https://github.com/{repo}/pull/{number}",
    )


def test_select_from_recent_changes() -> None:
    events = [
        _event("microsoft/agent-framework", ["python/x.py", "python/y.py"]),
        _event("google/adk-python", ["src/z.py"], number=2),
    ]
    selector = RegionSelector(max_regions=5)
    regions = selector.select(events)
    files = {(r.repo, r.file) for r in regions}
    assert ("microsoft/agent-framework", "python/x.py") in files
    assert ("microsoft/agent-framework", "python/y.py") in files


def test_caps_at_max_regions() -> None:
    events = [
        _event("a/a", [f"f{i}.py" for i in range(20)]),
    ]
    selector = RegionSelector(max_regions=5)
    regions = selector.select(events)
    assert len(regions) <= 5


def test_deduplicates_files() -> None:
    events = [
        _event("a/a", ["same.py"], number=1),
        _event("a/a", ["same.py"], number=2),
    ]
    selector = RegionSelector(max_regions=10)
    regions = selector.select(events)
    targets = [(r.repo, r.file) for r in regions]
    assert targets.count(("a/a", "same.py")) == 1


def test_excludes_test_and_doc_paths() -> None:
    events = [
        _event("a/a", ["src/core.py", "tests/test_x.py", "docs/y.md"]),
    ]
    selector = RegionSelector(max_regions=10)
    regions = selector.select(events)
    files = [r.file for r in regions]
    assert "src/core.py" in files
    assert "tests/test_x.py" not in files
    assert "docs/y.md" not in files
