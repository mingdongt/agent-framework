# Copyright (c) Microsoft. All rights reserved.

import logging
from pathlib import Path
from typing import Any, Protocol

from af_watch.models import CodeRegion, Hypothesis

_LOG = logging.getLogger(__name__)


class _LLMProto(Protocol):
    async def complete_json(self, *, system: str, user: str, max_retries: int = 2) -> Any: ...


class PersonaRunner:
    def __init__(self, *, llm: _LLMProto) -> None:
        self._llm = llm

    async def run(
        self,
        persona_path: Path,
        *,
        region: CodeRegion,
        code: str,
    ) -> list[Hypothesis]:
        system = persona_path.read_text(encoding="utf-8")
        user = self._build_user(region=region, code=code)

        try:
            raw = await self._llm.complete_json(system=system, user=user)
        except Exception as exc:
            _LOG.warning("persona %s failed on %s: %s", persona_path.stem, region.file, exc)
            return []

        items = self._normalize(raw)
        out: list[Hypothesis] = []
        for item in items:
            required = ("invariant", "violation_condition", "repro_sketch", "severity", "confidence")
            if any(item.get(k) in (None, "") for k in required):
                continue
            try:
                out.append(Hypothesis(
                    region_id=region.id or "",
                    repo=region.repo,
                    file=region.file,
                    persona=persona_path.stem,
                    invariant=item["invariant"],
                    violation_condition=item["violation_condition"],
                    repro_sketch=item["repro_sketch"],
                    severity=item["severity"],
                    confidence=float(item["confidence"]),
                ))
            except Exception as exc:
                _LOG.info("persona %s: hypothesis failed validation: %s", persona_path.stem, exc)
        return out

    @staticmethod
    def _build_user(*, region: CodeRegion, code: str) -> str:
        return (
            f"# Code region\n"
            f"Repo: {region.repo}\n"
            f"File: {region.file}\n"
            f"Recent change context: {region.recent_change_context}\n"
            f"Selection reason: {region.selection_reason}\n\n"
            f"## Source\n```\n{code}\n```\n\n"
            "Respond with JSON only — a list of hypothesis objects, or "
            "{\"hypotheses\": [...]}. Empty list if nothing flagged."
        )

    @staticmethod
    def _normalize(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            if "hypotheses" in raw:
                return raw["hypotheses"] or []
            if "invariant" in raw:
                return [raw]
        return []
