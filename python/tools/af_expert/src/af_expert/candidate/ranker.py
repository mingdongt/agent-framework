from __future__ import annotations

from dataclasses import dataclass

from af_expert.candidate.model import Candidate


PRIORITY_WEIGHTS = {"high": 1.0, "normal": 0.5, "low": 0.0}


@dataclass(frozen=True)
class RankWeights:
    w_conf: float = 0.35
    w_nov: float = 0.20
    w_act: float = 0.25
    w_rep: float = 0.15
    w_pri: float = 0.05


def score_candidate(
    c: Candidate, weights: RankWeights, repo_priority: dict[str, str] | None = None
) -> float:
    pri_value = 0.5
    if repo_priority is not None:
        priority = repo_priority.get(c.target_repo, "normal")
        pri_value = PRIORITY_WEIGHTS.get(priority, 0.5)
    return (
        weights.w_conf * c.confidence
        + weights.w_nov * c.novelty
        + weights.w_act * c.actionability
        + weights.w_rep * c.strategy_reputation
        + weights.w_pri * pri_value
    )


def rank_candidates(
    candidates: list[Candidate],
    *,
    weights: RankWeights | None = None,
    repo_priority: dict[str, str] | None = None,
) -> list[Candidate]:
    if weights is None:
        weights = RankWeights()
    return sorted(
        candidates,
        key=lambda c: score_candidate(c, weights, repo_priority),
        reverse=True,
    )
