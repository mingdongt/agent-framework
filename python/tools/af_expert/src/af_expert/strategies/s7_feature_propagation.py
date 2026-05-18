from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.llm import parse_json_block
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)


_FEAT_TITLE_RE = re.compile(r"^(feat|feature)[\(:]", re.IGNORECASE)
_FIX_TITLE_RE = re.compile(r"^(fix|bug|hotfix)[\(:]", re.IGNORECASE)
_FEAT_LABELS = {"enhancement", "feature", "new feature"}


def is_likely_feature_pr(title: str, labels: list[str]) -> bool:
    if _FIX_TITLE_RE.search(title or ""):
        return False
    if _FEAT_TITLE_RE.search(title or ""):
        return True
    if any(lab.lower() in _FEAT_LABELS for lab in labels):
        return True
    return False


def extract_feature_prompt(*, title: str, body: str, diff: str) -> str:
    return (
        "You will be given the title, body, and diff of a merged feature PR.\n"
        "Extract a concise feature identifier suitable for cross-repo propagation discussion.\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- feature_name: short snake_case identifier\n"
        "- summary: 1-2 sentences explaining what the feature does\n\n"
        f"TITLE:\n{title}\n\n"
        f"BODY:\n{body}\n\n"
        f"DIFF (truncated):\n{(diff or '')[:6000]}\n"
    )


def sister_check_prompt(*, framework: str, feature_name: str, summary: str) -> str:
    return (
        f"You are checking whether framework {framework} already has an equivalent of feature "
        f"'{feature_name}'.\n\n"
        f"Feature summary: {summary}\n\n"
        "Decide whether it has an equivalent capability based on your training-time knowledge.\n\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- has_equivalent: true | false\n"
        "- confidence: float 0.0-1.0\n"
        "- reasoning: 2-3 sentences\n"
    )


class FeaturePropagationStrategy(Strategy):
    name = "s7_feature_propagation"

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        produced: list[Candidate] = []
        all_repos = [r.owner_repo for r in self.config.repos]

        for source_repo in deltas.repos_with_new_prs:
            for pr in self.events.query_recent_prs(source_repo, since=deltas.since, only_merged=True):
                raw_labels = pr.get("labels") or "[]"
                try:
                    labels = json.loads(raw_labels) if isinstance(raw_labels, str) else raw_labels
                except json.JSONDecodeError:
                    labels = []
                if not is_likely_feature_pr(pr["title"], labels):
                    continue

                feature = self._extract_feature(pr)
                if feature is None:
                    continue

                for target in all_repos:
                    if target == source_repo:
                        continue
                    verdict = self._check_sister(target, feature)
                    if verdict is None or verdict.get("has_equivalent"):
                        continue
                    candidate = self._build_candidate(
                        source_repo=source_repo, source_pr=pr,
                        target_repo=target, feature=feature, verdict=verdict,
                    )
                    self.candidates.append(candidate)
                    produced.append(candidate)

        return produced

    def _extract_feature(self, pr: dict[str, Any]) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You extract feature identifiers from merged feature PRs.",
                user=extract_feature_prompt(
                    title=pr["title"], body=pr.get("body") or "", diff=pr.get("diff") or "",
                ),
                caller_label=f"s7.extract[{pr.get('repo')}#{pr['number']}]",
            )
            data = parse_json_block(resp.text)
            return {"feature_name": data["feature_name"], "summary": data["summary"]}
        except Exception as e:
            log.warning("S7 feature extract failed: %s", e)
            return None

    def _check_sister(self, framework: str, feature: dict[str, Any]) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You check whether a framework already has an equivalent of a given feature.",
                user=sister_check_prompt(
                    framework=framework,
                    feature_name=feature["feature_name"],
                    summary=feature["summary"],
                ),
                caller_label=f"s7.check[{framework}/{feature['feature_name']}]",
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("S7 sister check failed for %s: %s", framework, e)
            return None

    def _build_candidate(
        self, *, source_repo: str, source_pr: dict[str, Any], target_repo: str,
        feature: dict[str, Any], verdict: dict[str, Any],
    ) -> Candidate:
        return Candidate(
            id=f"s7-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=target_repo,
            category="feature",
            title=f"Propose {feature['feature_name']} for {target_repo}",
            description=(
                f"Source: {source_repo}#{source_pr['number']} introduced "
                f"'{feature['feature_name']}'.\n\n"
                f"Feature summary: {feature['summary']}\n\n"
                f"Target verdict: {verdict.get('reasoning', '')} "
                f"(confidence {float(verdict.get('confidence', 0.0)):.2f})"
            ),
            suggested_action=(
                f"Open an issue / RFC in {target_repo} proposing a similar feature. "
                f"DO NOT submit a drop-in PR — feature proposals need design alignment first."
            ),
            evidence_urls=[source_pr.get("url", "")],
            evidence_snippets=[],
            confidence=float(verdict.get("confidence", 0.5)),
            novelty=0.7,
            actionability=0.4,
            strategy_reputation=0.5,
            status="new",
        )
