# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


class AttemptOutcome(StrEnum):
    PR_OPENED = "pr_opened"
    GAVE_UP = "gave_up"
    ERROR = "error"
    BRANCH_PUSHED_NO_PR = "branch_pushed_no_pr"


class IssueRef(BaseModel):
    repo: str
    number: int

    @property
    def key(self) -> str:
        return f"{self.repo}#{self.number}"


class Issue(BaseModel):
    ref: IssueRef
    title: str
    body: str
    labels: list[str] = []
    comments_count: int = 0
    created_at: datetime | None = None


class ScoreResult(BaseModel):
    ref: IssueRef
    score: int
    reason: str
    suggested_files: list[str] = []


class FixResult(BaseModel):
    success: bool
    ref: IssueRef
    workspace: Path
    diff: str = ""
    summary: str | None = None
    trajectory_excerpt: str | None = None
    reason: str | None = None
    gave_up: bool = False


class PRResult(BaseModel):
    number: int
    url: str


class StateEntry(BaseModel):
    first_attempted: datetime
    last_attempted: datetime
    attempt_count: int
    outcome: AttemptOutcome
    branch: str | None = None
    pr_url: str | None = None
    give_up_reason: str | None = None
