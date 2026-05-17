# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from pathlib import Path
from typing import Any, Protocol

import yaml

from af_watch.corpus_loader import CorpusSnapshot
from af_watch.models import Opportunity, OpportunityType

_LOG = logging.getLogger(__name__)


class _LLMProto(Protocol):
    async def complete_json(self, *, system: str, user: str, max_retries: int = 2) -> Any: ...


class QuestionRunner:
    def __init__(self, *, llm: _LLMProto) -> None:
        self._llm = llm

    async def run(
        self,
        question_path: Path,
        *,
        snapshot: CorpusSnapshot,
        home_repo: str,
    ) -> list[Opportunity]:
        prompt = question_path.read_text(encoding="utf-8")
        system = self._extract_section(prompt, "System prompt")
        user = self._build_user_context(question_name=question_path.stem, snapshot=snapshot, home=home_repo)

        try:
            raw = await self._llm.complete_json(system=system, user=user)
        except Exception as exc:
            _LOG.warning("question %s failed: %s", question_path.stem, exc)
            return []

        return self._parse_opportunities(raw, question_name=question_path.stem)

    @staticmethod
    def _extract_section(markdown: str, heading: str) -> str:
        lines = markdown.splitlines()
        capture = False
        out: list[str] = []
        for line in lines:
            if line.strip().startswith(f"## {heading}"):
                capture = True
                continue
            if capture and line.startswith("## "):
                break
            if capture:
                out.append(line)
        return "\n".join(out).strip()

    @staticmethod
    def _build_user_context(*, question_name: str, snapshot: CorpusSnapshot, home: str) -> str:
        domain = snapshot.domain_maps.get(home, "(home domain map missing)")
        matrix = yaml.safe_dump(snapshot.comparison_matrix, sort_keys=False)
        intel = "\n\n".join(snapshot.industry_intel.values())[:20_000]
        return (
            f"# Question: {question_name}\n"
            f"# Home repo: {home}\n\n"
            f"## Home domain map\n{domain}\n\n"
            f"## Comparison matrix\n```yaml\n{matrix}\n```\n\n"
            f"## Industry intel\n{intel}\n"
        )

    def _parse_opportunities(self, raw: dict[str, Any], *, question_name: str) -> list[Opportunity]:
        items = raw.get("opportunities", [])
        out: list[Opportunity] = []
        for item in items:
            type_str = item.get("type")
            try:
                otype = OpportunityType(type_str)
            except ValueError:
                _LOG.info("question %s: unknown opportunity type %r", question_name, type_str)
                continue
            required = ("target", "action", "evidence", "effort", "risk", "rationale")
            if any(item.get(k) in (None, "") for k in required):
                _LOG.info("question %s: opportunity missing required slot", question_name)
                continue
            try:
                opp = Opportunity(
                    id=f"{question_name}-{str(uuid.uuid4())[:6]}",
                    type=otype,
                    target=item["target"],
                    action=item["action"],
                    evidence=item["evidence"],
                    effort=item["effort"],
                    risk=item["risk"],
                    risk_rationale=item.get("risk_rationale", ""),
                    rationale=item["rationale"],
                    tier=4,
                )
                out.append(opp)
            except Exception as exc:
                _LOG.info("question %s: opportunity failed validation: %s", question_name, exc)
        return out
