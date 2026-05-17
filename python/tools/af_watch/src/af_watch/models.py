# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OpportunityType(str, Enum):
    BUG_FIX = "bug-fix"
    BUG_PORT = "bug-port"
    FEATURE_PARITY = "feature-parity"
    INDUSTRY_ADAPT = "industry-adapt"
    DESIGN_BORROW = "design-borrow"
    DOCS_SAMPLE = "docs-sample"
    DRIFT_DECISION = "drift-decision"


class ActivityEvent(BaseModel):
    repo: str
    type: Literal["pr_merged", "issue_closed", "release"]
    number: int | None = None
    title: str
    timestamp: datetime
    author: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    body: str = ""
    url: str


class IndustryEntry(BaseModel):
    timestamp: datetime
    source: str
    title: str
    summary: str
    url: str


class CodeRegion(BaseModel):
    id: str | None = None
    repo: str
    file: str
    line_start: int
    line_end: int
    selection_reason: str
    recent_change_context: str = ""


class Hypothesis(BaseModel):
    region_id: str
    repo: str
    file: str
    persona: str
    invariant: str
    violation_condition: str
    repro_sketch: str
    severity: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0.0)

    @field_validator("confidence", mode="after")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class Opportunity(BaseModel):
    id: str
    type: OpportunityType
    target: str
    action: str
    evidence: str
    effort: str
    risk: Literal["very low", "low", "medium", "high"]
    risk_rationale: str = ""
    rationale: str
    tier: int = Field(ge=1, le=6)
    repro_status: Literal["confirmed", "attempted_failed", "attempted_timeout", "not_attempted"] = "not_attempted"
    repro_artifact: str | None = None
    supporting_personas: list[str] = Field(default_factory=list)
    related_activity: list[str] = Field(default_factory=list)
    handoff_command: str | None = None


class BriefingData(BaseModel):
    window_start: datetime
    window_end: datetime
    opportunities: list[Opportunity]
    industry_highlights: list[IndustryEntry] = Field(default_factory=list)
    activity_summary: dict[str, int] = Field(default_factory=dict)
