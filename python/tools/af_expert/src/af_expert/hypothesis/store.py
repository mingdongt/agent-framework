from __future__ import annotations

import json
from pathlib import Path

from af_expert.config import _state_dir
from af_expert.hypothesis.model import Hypothesis, Verification
from af_expert.state import atomic_write


class HypothesisStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path else _state_dir() / "hypotheses.json"

    def _load(self) -> dict[str, Hypothesis]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {hid: Hypothesis.model_validate(d) for hid, d in raw.get("hypotheses", {}).items()}

    def _save(self, hs: dict[str, Hypothesis]) -> None:
        payload = {
            "version": 1,
            "hypotheses": {hid: h.model_dump() for hid, h in hs.items()},
        }
        atomic_write(self.path, json.dumps(payload, indent=2, sort_keys=True, default=str))

    def list_all(self) -> list[Hypothesis]:
        return list(self._load().values())

    def list_active(self) -> list[Hypothesis]:
        return [h for h in self._load().values() if h.status == "active"]

    def get(self, hid: str) -> Hypothesis | None:
        return self._load().get(hid)

    def upsert(self, h: Hypothesis) -> None:
        hs = self._load()
        hs[h.id] = h
        self._save(hs)

    def attach_verification(self, hid: str, v: Verification) -> None:
        hs = self._load()
        if hid not in hs:
            raise KeyError(f"Hypothesis {hid!r} not found")
        hs[hid].verifications[v.repo] = v
        self._save(hs)

    def unverified_repos(self, hid: str, *, all_repos: list[str]) -> list[str]:
        hs = self._load()
        if hid not in hs:
            return all_repos
        verified = set(hs[hid].verifications.keys())
        return [r for r in all_repos if r not in verified]

    def archive(self, hid: str) -> None:
        hs = self._load()
        if hid in hs:
            hs[hid].status = "archived"
            self._save(hs)
