# Copyright (c) Microsoft. All rights reserved.

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class State:
    VERSION = 1

    def __init__(self, path: Path, data: dict[str, Any]) -> None:
        self._path = path
        self._data = data

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls(path, {
                "version": cls.VERSION,
                "last_run": None,
                "corpus_last_refreshed": {},
                "decisions_log": [],
            })
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(path, raw)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, default=str),
            encoding="utf-8",
        )

    @property
    def last_run(self) -> dict[str, Any] | None:
        return self._data.get("last_run")

    @property
    def decisions_log(self) -> list[dict[str, Any]]:
        return self._data.setdefault("decisions_log", [])

    @property
    def corpus_last_refreshed(self) -> dict[str, str]:
        return self._data.setdefault("corpus_last_refreshed", {})

    def record_run(
        self,
        *,
        started_at: datetime,
        completed_at: datetime,
        window: str,
        opp_count: int,
        report_path: Path,
    ) -> None:
        self._data["last_run"] = {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "window": window,
            "opp_count": opp_count,
            "report_path": str(report_path),
        }

    def log_decision(self, *, opp_id: str, action: str, note: str = "") -> None:
        self.decisions_log.append({
            "opp_id": opp_id,
            "action": action,
            "note": note,
            "logged_at": datetime.now(tz=timezone.utc).isoformat(),
        })

    def mark_corpus_refreshed(self, path: str, date: str) -> None:
        self.corpus_last_refreshed[path] = date
