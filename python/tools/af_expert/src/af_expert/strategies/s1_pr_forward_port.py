from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.llm import parse_json_block
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

# Heuristic: title looks like a bug fix
_FIX_TITLE_PATTERN = re.compile(r"^(fix|bug|hotfix)[\(:]", re.IGNORECASE)
_BUG_LABELS = {"bug", "fix", "p0", "p1", "regression"}


def is_likely_bug_fix(title: str, labels: list[str]) -> bool:
    if _FIX_TITLE_PATTERN.search(title or ""):
        return True
    if any(lab.lower() in _BUG_LABELS for lab in labels):
        return True
    if title and title.lower().startswith("bug"):
        return True
    return False


@dataclass(frozen=True)
class BugPattern:
    pattern_name: str
    failure_mode: str
    code_shape_hints: list[str]
    fix_shape_hints: list[str]


def extract_pattern_prompt(*, title: str, body: str, diff: str) -> str:
    return (
        "You will be given the title, body, and diff of a merged bug-fix PR.\n"
        "Extract the bug pattern as JSON with these fields:\n"
        "- pattern_name: a short identifier (snake_case)\n"
        "- failure_mode: one-paragraph description of what was broken and why\n"
        "- code_shape_hints: list of 3-6 short strings describing what to grep for in another codebase\n"
        "- fix_shape_hints: list of 2-4 short strings describing the shape of a fix\n\n"
        "Respond with ONLY the JSON in a fenced ```json block.\n\n"
        f"TITLE:\n{title}\n\n"
        f"BODY:\n{body}\n\n"
        f"DIFF:\n{diff[:8000]}\n"
    )


def match_prompt(*, pattern: BugPattern, target_repo: str) -> str:
    return (
        f"You are checking whether a bug pattern exists in repository {target_repo}.\n\n"
        f"Pattern name: {pattern.pattern_name}\n"
        f"Failure mode: {pattern.failure_mode}\n"
        f"What to look for: {', '.join(pattern.code_shape_hints)}\n"
        f"What a fix would look like: {', '.join(pattern.fix_shape_hints)}\n\n"
        "Based on your training-time knowledge of this repository's structure "
        "(do NOT fabricate exact line numbers; only mention file paths you actually recall), "
        "decide whether the same bug shape is plausibly present.\n\n"
        "Respond with ONLY a fenced ```json block with fields:\n"
        "- matches: true | false\n"
        "- confidence: float 0.0-1.0 (be conservative; default 0.3 if uncertain)\n"
        "- target_files: list of likely file paths (use [] if uncertain)\n"
        "- reasoning: 2-3 sentences\n"
    )


class PRForwardPortStrategy(Strategy):
    name = "s1_pr_forward_port"

    def __init__(
        self,
        *args: Any,
        confidence_threshold: float = 0.5,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.confidence_threshold = confidence_threshold

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        produced: list[Candidate] = []
        all_repos = [r.owner_repo for r in self.config.repos]

        for source_repo in deltas.repos_with_new_prs:
            for pr in self.events.query_recent_prs(source_repo, since=deltas.since, only_merged=True):
                labels = self._parse_labels(pr["labels"])
                if not is_likely_bug_fix(pr["title"], labels):
                    continue
                pattern = self._extract_pattern(pr)
                if pattern is None:
                    continue

                for target_repo in all_repos:
                    if target_repo == source_repo:
                        continue
                    match = self._match_in_repo(pattern, target_repo)
                    if match is None:
                        continue
                    if not match.get("matches"):
                        continue
                    conf = float(match.get("confidence", 0.0))
                    if conf < self.confidence_threshold:
                        continue
                    candidate = self._build_candidate(
                        source_repo=source_repo,
                        source_pr=pr,
                        target_repo=target_repo,
                        pattern=pattern,
                        match=match,
                    )
                    self.candidates.append(candidate)
                    produced.append(candidate)

        return produced

    def _parse_labels(self, raw: Any) -> list[str]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return []

    def _extract_pattern(self, pr: dict[str, Any]) -> BugPattern | None:
        prompt = extract_pattern_prompt(
            title=pr["title"], body=pr.get("body") or "", diff=pr.get("diff") or ""
        )
        try:
            resp = self.llm.complete(
                system="You are a senior engineer who extracts bug patterns from PR diffs.",
                user=prompt,
            )
            data = parse_json_block(resp.text)
            return BugPattern(
                pattern_name=data["pattern_name"],
                failure_mode=data["failure_mode"],
                code_shape_hints=list(data.get("code_shape_hints", [])),
                fix_shape_hints=list(data.get("fix_shape_hints", [])),
            )
        except Exception as e:
            log.warning("Pattern extraction failed for %s#%d: %s", pr["repo"], pr["number"], e)
            return None

    def _match_in_repo(self, pattern: BugPattern, target_repo: str) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You are evaluating whether a known bug pattern exists in a given repository.",
                user=match_prompt(pattern=pattern, target_repo=target_repo),
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("Match check failed for %s: %s", target_repo, e)
            return None

    def _build_candidate(
        self,
        *,
        source_repo: str,
        source_pr: dict[str, Any],
        target_repo: str,
        pattern: BugPattern,
        match: dict[str, Any],
    ) -> Candidate:
        return Candidate(
            id=f"s1-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=target_repo,
            target_files=list(match.get("target_files", [])),
            category="bug",
            title=f"Possible {pattern.pattern_name} in {target_repo}",
            description=(
                f"Pattern: {pattern.pattern_name}\n\n"
                f"Failure mode: {pattern.failure_mode}\n\n"
                f"Reasoning: {match.get('reasoning', '')}\n\n"
                f"Source PR (already merged): {source_repo}#{source_pr['number']}"
            ),
            suggested_action=f"Port the fix shape from {source_repo}#{source_pr['number']}: "
            + "; ".join(pattern.fix_shape_hints),
            evidence_urls=[source_pr.get("url", "")],
            evidence_snippets=[],
            confidence=float(match.get("confidence", 0.0)),
            novelty=0.3,
            actionability=0.75,
            strategy_reputation=0.5,
            status="new",
        )
