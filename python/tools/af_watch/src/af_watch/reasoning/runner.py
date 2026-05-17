# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Protocol, TypeVar

from af_watch.corpus_loader import CorpusSnapshot
from af_watch.models import CodeRegion, Hypothesis, Opportunity

_LOG = logging.getLogger(__name__)

T = TypeVar("T")


class _QuestionRunner(Protocol):
    async def run(self, question_path: Path, *, snapshot: CorpusSnapshot, home_repo: str) -> list[Opportunity]: ...


class _PersonaRunner(Protocol):
    async def run(self, persona_path: Path, *, region: CodeRegion, code: str) -> list[Hypothesis]: ...


class ReasoningRunner:
    def __init__(
        self,
        *,
        question_runner: _QuestionRunner,
        persona_runner: _PersonaRunner,
        questions_dir: Path,
        personas_dir: Path,
        code_reader: Callable[[str, str], str],
    ) -> None:
        self._qr = question_runner
        self._pr = persona_runner
        self._qdir = questions_dir
        self._pdir = personas_dir
        self._read = code_reader

    async def run(
        self,
        *,
        snapshot: CorpusSnapshot,
        home_repo: str,
        regions: list[CodeRegion],
    ) -> tuple[list[Opportunity], list[Hypothesis]]:
        question_paths = sorted(self._qdir.glob("*.md"))
        persona_paths = sorted(self._pdir.glob("*.md"))

        question_tasks = [
            self._safe(self._qr.run(qp, snapshot=snapshot, home_repo=home_repo))
            for qp in question_paths
        ]
        persona_tasks = [
            self._safe(self._pr.run(pp, region=region, code=self._safe_read(region)))
            for region in regions
            for pp in persona_paths
        ]

        question_results = await asyncio.gather(*question_tasks)
        persona_results = await asyncio.gather(*persona_tasks)

        opps: list[Opportunity] = []
        for r in question_results:
            opps.extend(r or [])
        hyps: list[Hypothesis] = []
        for r in persona_results:
            hyps.extend(r or [])

        return opps, hyps

    def _safe_read(self, region: CodeRegion) -> str:
        try:
            return self._read(region.repo, region.file)
        except Exception as exc:
            _LOG.warning("failed to read %s:%s: %s", region.repo, region.file, exc)
            return ""

    @staticmethod
    async def _safe(coro: Awaitable[list[T]]) -> list[T]:
        try:
            return await coro
        except Exception as exc:
            _LOG.warning("reasoning task failed: %s", exc)
            return []
