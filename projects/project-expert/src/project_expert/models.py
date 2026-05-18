"""Data models for Project Expert."""
from pydantic import BaseModel


class IssueEntry(BaseModel):
    """GitHub issue entry model."""

    number: int
    title: str
    url: str
    state: str
