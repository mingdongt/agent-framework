from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.config import _state_dir
from af_expert.state import atomic_write


class CandidateStore:
    """Append-only JSONL per day. Status updates are stored in an overlay file."""

    def __init__(self, base: Path | None = None) -> None:
        self.base = base if base else _state_dir() / "candidates"
        self.base.mkdir(parents=True, exist_ok=True)
        self.overlay_path = self.base / "status_overlay.json"

    def _file_for(self, when: datetime) -> Path:
        return self.base / f"{when.date().isoformat()}.jsonl"

    def append(self, candidate: Candidate) -> None:
        path = self._file_for(candidate.discovered_at)
        with path.open("a", encoding="utf-8") as f:
            f.write(candidate.model_dump_json() + "\n")

    def _load_overlay(self) -> dict[str, dict[str, Any]]:
        if not self.overlay_path.exists():
            return {}
        return json.loads(self.overlay_path.read_text(encoding="utf-8"))

    def _save_overlay(self, overlay: dict[str, dict[str, Any]]) -> None:
        atomic_write(self.overlay_path, json.dumps(overlay, indent=2, sort_keys=True))

    def _apply_overlay(self, c: Candidate) -> Candidate:
        overlay = self._load_overlay()
        update = overlay.get(c.id)
        if update is None:
            return c
        # Re-validate by merging fields
        merged = c.model_dump()
        merged.update(update)
        return Candidate.model_validate(merged)

    def list_since(self, since: datetime) -> Iterator[Candidate]:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        cutoff_date = since.date()
        for path in sorted(self.base.glob("*.jsonl")):
            try:
                file_date = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if file_date < cutoff_date:
                continue
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    c = Candidate.model_validate_json(line)
                    if c.discovered_at >= since:
                        yield self._apply_overlay(c)

    def list_today(self) -> Iterator[Candidate]:
        today_start = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return self.list_since(today_start)

    def get(self, candidate_id: str) -> Candidate | None:
        for path in sorted(self.base.glob("*.jsonl"), reverse=True):
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    c = Candidate.model_validate_json(line)
                    if c.id == candidate_id:
                        return self._apply_overlay(c)
        return None

    def update_status(
        self, candidate_id: str, *, status: str, notes: str | None = None
    ) -> None:
        overlay = self._load_overlay()
        existing = overlay.get(candidate_id, {})
        existing["status"] = status
        if notes is not None:
            existing["notes"] = notes
        overlay[candidate_id] = existing
        self._save_overlay(overlay)
