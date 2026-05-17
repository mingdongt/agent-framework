# Copyright (c) Microsoft. All rights reserved.

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from af_fix.models import AttemptOutcome, IssueRef, StateEntry

STATE_VERSION = 2


class State(BaseModel):
    path: Path
    attempts: dict[str, StateEntry] = {}

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls(path=path, attempts={})
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") != STATE_VERSION:
            raise ValueError(f"Unsupported state version: {raw.get('version')}")
        attempts = {k: StateEntry.model_validate(v) for k, v in raw.get("attempts", {}).items()}
        return cls(path=path, attempts=attempts)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STATE_VERSION,
            "attempts": {k: v.model_dump(mode="json") for k, v in self.attempts.items()},
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def record_attempt(
        self,
        ref: IssueRef,
        *,
        outcome: AttemptOutcome,
        branch: str | None,
        now: datetime,
        pr_url: str | None = None,
        give_up_reason: str | None = None,
    ) -> None:
        existing = self.attempts.get(ref.key)
        if existing is None:
            self.attempts[ref.key] = StateEntry(
                first_attempted=now,
                last_attempted=now,
                attempt_count=1,
                outcome=outcome,
                branch=branch,
                pr_url=pr_url,
                give_up_reason=give_up_reason,
            )
        else:
            existing.last_attempted = now
            existing.attempt_count += 1
            existing.outcome = outcome
            if branch is not None:
                existing.branch = branch
            if pr_url is not None:
                existing.pr_url = pr_url
            if give_up_reason is not None:
                existing.give_up_reason = give_up_reason

    def should_skip(self, ref: IssueRef, *, retry_failed: bool = False) -> bool:
        entry = self.attempts.get(ref.key)
        if entry is None:
            return False
        if entry.outcome == AttemptOutcome.PR_OPENED:
            return True
        return not (retry_failed and entry.outcome in {AttemptOutcome.GAVE_UP, AttemptOutcome.ERROR})
