from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from af_expert.candidate.model import Candidate
from af_expert.candidate.store import CandidateStore
from af_expert.config import Config
from af_expert.ingestion.store import EventStore
from af_expert.llm import LLM


@dataclass
class IngestionDeltas:
    """Container for what changed in this tick.

    For Wave 1 we only need to know which repos had new merged PRs.
    Future strategies may need more (releases, architecture changes, etc.).
    """
    since: datetime
    repos_with_new_prs: list[str]


class Strategy(ABC):
    name: str

    def __init__(
        self,
        *,
        config: Config,
        events: EventStore,
        candidates: CandidateStore,
        llm: LLM,
    ) -> None:
        self.config = config
        self.events = events
        self.candidates = candidates
        self.llm = llm

    @abstractmethod
    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        """Called after the daily tick finishes ingestion. Return new candidates."""

    def on_weekly_tick(self) -> list[Candidate]:
        """Override for strategies that run weekly (e.g., S5). Default: no-op."""
        return []

    def on_demand(self, args: dict[str, object]) -> list[Candidate]:
        """Override for strategies that support operator-initiated runs. Default: no-op."""
        return []
