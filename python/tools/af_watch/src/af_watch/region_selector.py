# Copyright (c) Microsoft. All rights reserved.

import uuid

from af_watch.models import ActivityEvent, CodeRegion

_EXCLUDE_PREFIXES = ("tests/", "test/", "docs/", "examples/", ".github/")
_EXCLUDE_SUFFIXES = (".md", ".rst", ".txt", ".yaml", ".yml", ".toml", ".lock")


class RegionSelector:
    def __init__(self, *, max_regions: int = 15) -> None:
        self._max = max_regions

    def select(self, events: list[ActivityEvent]) -> list[CodeRegion]:
        seen: set[tuple[str, str]] = set()
        regions: list[CodeRegion] = []

        for ev in events:
            if ev.type != "pr_merged":
                continue
            for file in ev.files_changed:
                if self._exclude(file):
                    continue
                key = (ev.repo, file)
                if key in seen:
                    continue
                seen.add(key)
                regions.append(CodeRegion(
                    id=str(uuid.uuid4())[:8],
                    repo=ev.repo,
                    file=file,
                    line_start=1,
                    line_end=10_000,
                    selection_reason=f"changed in PR #{ev.number}",
                    recent_change_context=ev.title,
                ))
                if len(regions) >= self._max:
                    return regions

        return regions

    @staticmethod
    def _exclude(file: str) -> bool:
        normalized = file.replace("\\", "/")
        if any(normalized.startswith(p) for p in _EXCLUDE_PREFIXES):
            return True
        return any(normalized.endswith(s) for s in _EXCLUDE_SUFFIXES)
