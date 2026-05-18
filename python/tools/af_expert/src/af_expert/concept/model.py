from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


_CONCEPT_ID_RE = re.compile(r"^[a-z][a-z0-9._-]*[a-z0-9]$")


class ConceptImplementation(BaseModel):
    repo: str
    files: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    last_modified: str | None = None
    compliant: bool | None = None
    notes: str = ""


class Concept(BaseModel):
    id: str
    description: str
    spec_ref: str = ""
    tags: list[str] = Field(default_factory=list)
    implementations: dict[str, ConceptImplementation] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not _CONCEPT_ID_RE.match(v):
            raise ValueError(f"Concept id must be lowercase dot-separated, got {v!r}")
        return v
