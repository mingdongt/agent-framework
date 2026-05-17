# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from af_watch.exceptions import CorpusError


@dataclass(frozen=True)
class FeatureGap:
    feature: str
    description: str
    implemented_elsewhere: list[str]
    importance: str


@dataclass(frozen=True)
class CorpusSnapshot:
    domain_maps: dict[str, str]
    comparison_matrix: dict[str, dict[str, Any]]
    industry_intel: dict[str, str]

    def feature_gaps(self, *, home: str, threshold: float = 0.5) -> list[FeatureGap]:
        gaps: list[FeatureGap] = []
        for fname, fdata in self.comparison_matrix.items():
            frameworks = fdata.get("frameworks", {})
            home_status = frameworks.get(home, {}).get("status")
            if home_status != "not_implemented":
                continue
            others = [r for r, info in frameworks.items() if r != home]
            if not others:
                continue
            implemented_elsewhere = [
                r for r, info in frameworks.items()
                if r != home and info.get("status") in ("implemented", "in_progress")
            ]
            if len(implemented_elsewhere) / len(others) < threshold:
                continue
            gaps.append(FeatureGap(
                feature=fname,
                description=fdata.get("description", ""),
                implemented_elsewhere=implemented_elsewhere,
                importance=fdata.get("importance", "unknown"),
            ))
        return gaps


class CorpusLoader:
    def __init__(self, corpus_dir: Path) -> None:
        self._dir = corpus_dir

    def load(self) -> CorpusSnapshot:
        if not self._dir.exists():
            raise CorpusError(f"corpus directory missing: {self._dir}")
        return CorpusSnapshot(
            domain_maps=self._load_domain_maps(),
            comparison_matrix=self._load_matrix(),
            industry_intel=self._load_intel(),
        )

    def _load_domain_maps(self) -> dict[str, str]:
        dir_ = self._dir / "domain_map"
        if not dir_.exists():
            return {}
        out: dict[str, str] = {}
        for md in dir_.glob("*.md"):
            if md.name == "README.md":
                continue
            slug = md.stem
            if "__" not in slug:
                continue
            owner, name = slug.split("__", 1)
            repo = f"{owner}/{name}"
            out[repo] = md.read_text(encoding="utf-8")
        return out

    def _load_matrix(self) -> dict[str, dict[str, Any]]:
        path = self._dir / "comparison_matrix" / "features.yaml"
        if not path.exists():
            return {}
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise CorpusError(f"malformed features.yaml: {exc}") from exc

    def _load_intel(self) -> dict[str, str]:
        dir_ = self._dir / "industry_intel"
        if not dir_.exists():
            return {}
        out: dict[str, str] = {}
        for md in dir_.glob("*.md"):
            if md.name == "README.md":
                continue
            out[md.stem] = md.read_text(encoding="utf-8")
        return out
