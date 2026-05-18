from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.hypothesis.model import Hypothesis, Verification
from af_expert.hypothesis.store import HypothesisStore
from af_expert.llm import parse_json_block
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)


def verify_prompt(*, hypothesis: Hypothesis, repo: str, briefing: str | None) -> str:
    parts: list[str] = [
        f"You are verifying a hypothesis against the OSS repository '{repo}'.\n\n"
        f"Hypothesis (id={hypothesis.id}): {hypothesis.statement}\n\n"
        "Decide whether this repo's implementation is compliant, non_compliant, "
        "not_applicable (concept doesn't exist in this repo), or unclear.\n\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- outcome: \"compliant\" | \"non_compliant\" | \"not_applicable\" | \"unclear\"\n"
        "- reasoning: 2-3 sentences citing specific files / behaviors if possible\n"
        "- confidence: float 0.0-1.0\n\n"
    ]
    if briefing:
        parts.append("### Architecture briefing\n")
        parts.append(briefing[:6000])
        parts.append("\n")
    else:
        parts.append(
            "(No architecture briefing available — base your decision on training-time "
            "knowledge of this repo.)\n"
        )
    return "".join(parts)


def _load_briefing(repo: str) -> str | None:
    from af_expert.architecture.refresh import repo_briefing_path
    p = repo_briefing_path(repo)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


class HypothesisVerifyStrategy(Strategy):
    name = "s3_hypothesis_verify"

    def __init__(self, *args: Any, hypothesis_store: HypothesisStore, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.hypothesis_store = hypothesis_store

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        active = self.hypothesis_store.list_active()
        if not active:
            return []

        all_repos = [r.owner_repo for r in self.config.repos]
        if not all_repos:
            return []

        # Pick one (hypothesis, repo) pair to verify this tick
        for h in active:
            unverified = self.hypothesis_store.unverified_repos(h.id, all_repos=all_repos)
            if not unverified:
                continue
            target_repo = unverified[0]  # take first; could randomize in future
            return self._verify_one(h, target_repo)

        return []

    def _verify_one(self, h: Hypothesis, repo: str) -> list[Candidate]:
        briefing = _load_briefing(repo)
        try:
            resp = self.llm.complete(
                system="You are verifying an architectural hypothesis against an OSS repo.",
                user=verify_prompt(hypothesis=h, repo=repo, briefing=briefing),
                caller_label=f"s3.verify[{h.id}->{repo}]",
            )
            data = parse_json_block(resp.text)
        except Exception as e:
            log.warning("S3 verification failed for %s -> %s: %s", h.id, repo, e)
            return []

        outcome = data.get("outcome", "unclear")
        reasoning = data.get("reasoning", "")
        confidence = float(data.get("confidence", 0.5))

        v = Verification(
            repo=repo,
            verified_at=datetime.now(tz=timezone.utc).date().isoformat(),
            outcome=outcome,
            reasoning=reasoning,
            confidence=confidence,
        )
        self.hypothesis_store.attach_verification(h.id, v)

        log.info("S3 %s -> %s: %s (conf %.2f)", h.id, repo, outcome, confidence)

        if outcome != "non_compliant":
            return []

        candidate = self._build_candidate(h=h, repo=repo, v=v)
        self.candidates.append(candidate)
        v.candidate_id = candidate.id
        self.hypothesis_store.attach_verification(h.id, v)
        return [candidate]

    def _build_candidate(self, *, h: Hypothesis, repo: str, v: Verification) -> Candidate:
        return Candidate(
            id=f"s3-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=repo,
            category="bug",
            title=f"Hypothesis verified non-compliant: {h.id}",
            description=(
                f"Hypothesis: {h.statement}\n\n"
                f"Verification reasoning: {v.reasoning}\n\n"
                f"Confidence: {v.confidence:.2f}"
            ),
            suggested_action=(
                f"Review {repo}'s implementation against the hypothesis. "
                f"If genuinely non-compliant, propose a fix PR."
            ),
            evidence_urls=[f"https://github.com/{repo}"],
            evidence_snippets=[],
            confidence=v.confidence,
            novelty=0.7,
            actionability=0.5,
            strategy_reputation=0.5,
            status="new",
        )
