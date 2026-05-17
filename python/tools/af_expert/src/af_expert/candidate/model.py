from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["bug", "feature", "maintenance", "consolidation"]
Status = Literal["new", "reviewed", "accepted", "rejected", "shipped"]


class Candidate(BaseModel):
    id: str
    discovered_at: datetime
    strategy: str

    target_repo: str
    target_files: list[str] = Field(default_factory=list)
    target_lines: list[tuple[int, int]] = Field(default_factory=list)
    category: Category

    title: str
    description: str
    suggested_action: str

    evidence_urls: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)

    confidence: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    actionability: float = Field(ge=0.0, le=1.0)
    strategy_reputation: float = Field(ge=0.0, le=1.0)

    status: Status = "new"
    notes: str = ""
