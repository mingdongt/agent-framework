from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.concept.store import ConceptGraphStore
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

DEFAULT_STALENESS_DAYS = 180


def find_lagging_impls(
    *, store: ConceptGraphStore, now: datetime, staleness_days: int = DEFAULT_STALENESS_DAYS
) -> list[tuple[str, ConceptImplementation]]:
    cutoff = now - timedelta(days=staleness_days)
    lagging: list[tuple[str, ConceptImplementation]] = []
    for concept in store.list_all():
        for repo, impl in concept.implementations.items():
            if not impl.last_modified:
                continue
            try:
                last = datetime.fromisoformat(impl.last_modified).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if last < cutoff:
                lagging.append((concept.id, impl))
    return lagging


class StructuralDiffStrategy(Strategy):
    name = "s2_structural_diff"

    def __init__(self, *args: Any, concept_store: ConceptGraphStore, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.concept_store = concept_store

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        return []

    def on_weekly_tick(self, now: datetime | None = None) -> list[Candidate]:
        if now is None:
            now = datetime.now(tz=timezone.utc)

        produced: list[Candidate] = []
        tracked = {r.owner_repo for r in self.config.repos}

        lagging = find_lagging_impls(store=self.concept_store, now=now)
        for concept_id, impl in lagging:
            if impl.repo not in tracked:
                continue
            concept = self.concept_store.get(concept_id)
            if concept is None:
                continue
            candidate = self._build_candidate(concept=concept, impl=impl, now=now)
            self.candidates.append(candidate)
            produced.append(candidate)
            log.info(
                "S2 %s: %s lagging on %s (last_modified=%s)",
                concept_id, impl.repo, concept.spec_ref or "(no spec)", impl.last_modified,
            )

        return produced

    def _build_candidate(
        self, *, concept: Concept, impl: ConceptImplementation, now: datetime
    ) -> Candidate:
        return Candidate(
            id=f"s2-{uuid.uuid4().hex[:12]}",
            discovered_at=now,
            strategy=self.name,
            target_repo=impl.repo,
            target_files=impl.files,
            category="consolidation",
            title=f"{impl.repo} lagging on {concept.id}",
            description=(
                f"Concept '{concept.id}' ({concept.description}) "
                f"has not been updated in {impl.repo} since {impl.last_modified}. "
                f"Spec reference: {concept.spec_ref or 'none recorded'}.\n\n"
                f"Files: {', '.join(impl.files)}\n"
                f"Functions: {', '.join(impl.functions)}"
            ),
            suggested_action=(
                f"Review {concept.id} implementation in {impl.repo}; compare against "
                f"more recent implementations in sister repos to identify what needs porting."
            ),
            evidence_urls=[f"https://github.com/{impl.repo}"],
            evidence_snippets=[],
            confidence=0.5,
            novelty=0.7,
            actionability=0.4,
            strategy_reputation=0.5,
            status="new",
        )
