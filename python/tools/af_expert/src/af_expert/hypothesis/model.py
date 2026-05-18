from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


VerificationOutcome = Literal["compliant", "non_compliant", "not_applicable", "unclear"]
HypothesisStatus = Literal["active", "verified", "archived"]


class Verification(BaseModel):
    repo: str
    verified_at: str           # ISO date
    outcome: VerificationOutcome
    reasoning: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    candidate_id: str | None = None


class Hypothesis(BaseModel):
    id: str
    statement: str
    proposed_by: str           # "operator" | "s1_promotion" | etc.
    created_at: datetime
    status: HypothesisStatus = "active"
    tags: list[str] = Field(default_factory=list)
    verifications: dict[str, Verification] = Field(default_factory=dict)
    notes: str = ""
