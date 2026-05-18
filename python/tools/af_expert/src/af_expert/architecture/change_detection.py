from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any


log = logging.getLogger(__name__)

_DIFF_PATH_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


@dataclass
class DriftSignal:
    has_drift: bool
    touched_core_paths: set[str] = field(default_factory=set)
    triggering_prs: list[int] = field(default_factory=list)


def extract_changed_paths_from_diff(diff: str | None) -> set[str]:
    if not diff:
        return set()
    return set(_DIFF_PATH_RE.findall(diff))


def detect_architectural_drift(
    *, core_paths: list[str], prs: list[dict[str, Any]]
) -> DriftSignal:
    core_set = set(core_paths)
    touched: set[str] = set()
    triggering: list[int] = []

    for pr in prs:
        changed = extract_changed_paths_from_diff(pr.get("diff"))
        overlap = changed & core_set
        if overlap:
            touched.update(overlap)
            triggering.append(pr.get("number", -1))

    return DriftSignal(
        has_drift=bool(touched),
        touched_core_paths=touched,
        triggering_prs=triggering,
    )
