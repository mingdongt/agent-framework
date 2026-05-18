from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.framework_adapters.base import FrameworkAdapter
from af_expert.spec_corpus.base import SpecProperty
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)


class SpecConformanceStrategy(Strategy):
    name = "s5_spec_conformance"

    def __init__(
        self,
        *args: Any,
        adapter_registry: dict[str, FrameworkAdapter] | None = None,
        properties: list[SpecProperty] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if adapter_registry is None:
            from af_expert.framework_adapters.agent_framework import AgentFrameworkAdapter
            adapter_registry = {"microsoft/agent-framework": AgentFrameworkAdapter()}
        if properties is None:
            from af_expert.spec_corpus.mcp import MCP_PROPERTIES
            properties = list(MCP_PROPERTIES)
        self.adapter_registry = adapter_registry
        self.properties = properties

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        return []  # weekly

    def on_weekly_tick(self, now: datetime | None = None) -> list[Candidate]:
        if now is None:
            now = datetime.now(tz=timezone.utc)
        produced: list[Candidate] = []
        for repo_cfg in self.config.repos:
            framework = repo_cfg.owner_repo
            adapter = self.adapter_registry.get(framework)
            if adapter is None:
                log.debug("S5 skip %s: no adapter registered", framework)
                continue
            for prop in self.properties:
                try:
                    result = prop.run(adapter=adapter)
                except Exception as e:
                    log.warning("S5 %s on %s raised: %s", prop.full_id, framework, e)
                    continue
                if result.passed:
                    log.info("S5 %s on %s: PASS", prop.full_id, framework)
                    continue
                log.info("S5 %s on %s: FAIL — %s", prop.full_id, framework, result.message)
                candidate = self._build_candidate(framework, prop, result, now)
                self.candidates.append(candidate)
                produced.append(candidate)
        return produced

    def _build_candidate(
        self, framework: str, prop: SpecProperty, result: Any, now: datetime
    ) -> Candidate:
        return Candidate(
            id=f"s5-{uuid.uuid4().hex[:12]}",
            discovered_at=now,
            strategy=self.name,
            target_repo=framework,
            category="bug",
            title=f"Spec conformance failure: {prop.full_id} on {framework}",
            description=(
                f"Spec: {prop.spec}\n"
                f"Property: {prop.name}\n"
                f"Property description: {prop.description}\n\n"
                f"Failure message: {result.message}\n\n"
                "This is a strong-evidence candidate: the failure is reproducible "
                "via the adapter snippet below."
            ),
            suggested_action=(
                f"Investigate the framework code path corresponding to {prop.full_id}. "
                f"Use the snippet below to reproduce the failure locally before fixing."
            ),
            evidence_urls=[f"https://github.com/{framework}"],
            evidence_snippets=[result.repro_snippet or ""],
            confidence=0.95,                # high — backed by a failing test
            novelty=0.6,
            actionability=0.95,             # has repro
            strategy_reputation=0.5,
            status="new",
        )
