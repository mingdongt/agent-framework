from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from af_expert.candidate.model import Candidate
from af_expert.llm import parse_json_block
from af_expert.providers.poller import poll_provider
from af_expert.providers.sources import PROVIDER_SOURCES
from af_expert.strategies.base import IngestionDeltas, Strategy


log = logging.getLogger(__name__)

MAX_HTML_CHARS = 10000


def extract_release_summary_prompt(*, provider: str, html_body: str) -> str:
    return (
        f"You are extracting recent release information for the {provider} LLM provider.\n"
        "The following is the latest release-notes / changelog page (HTML).\n\n"
        "Identify whether there is a NEW release / API change in the last 14 days.\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- is_new_release: true | false\n"
        "- title: short headline (or empty string if no new release)\n"
        "- changes: list of objects with fields {name, description}\n\n"
        f"PAGE BODY (truncated):\n{html_body[:MAX_HTML_CHARS]}\n"
    )


def framework_check_prompt(*, framework: str, change_name: str, change_description: str) -> str:
    return (
        f"You are checking whether the framework {framework} already supports a new {change_name} "
        f"capability from an LLM provider.\n\n"
        f"Change name: {change_name}\n"
        f"Change description: {change_description}\n\n"
        "Based on your training-time knowledge of this framework's source code structure, "
        "decide whether this capability is plausibly already supported.\n\n"
        "Respond with ONLY a fenced ```json block:\n"
        "- supports: true | false\n"
        "- confidence: float 0.0-1.0\n"
        "- reasoning: 2-3 sentences\n"
    )


class ProviderReleaseStrategy(Strategy):
    name = "s4_provider_release"

    def on_ingestion_complete(self, deltas: IngestionDeltas) -> list[Candidate]:
        produced: list[Candidate] = []

        for source in PROVIDER_SOURCES:
            body = poll_provider(source)
            if not body:
                continue

            summary = self._extract_summary(source.name, body)
            if not summary or not summary.get("is_new_release"):
                continue

            changes = summary.get("changes", [])
            if not changes:
                continue

            log.info(
                "S4 %s: %d changes detected (%s)",
                source.name, len(changes), summary.get("title", "")
            )

            for change in changes:
                change_name = change.get("name", "")
                change_desc = change.get("description", "")
                if not change_name:
                    continue
                for repo_cfg in self.config.repos:
                    framework = repo_cfg.owner_repo
                    verdict = self._check_framework(framework, change_name, change_desc)
                    if verdict is None:
                        continue
                    if verdict.get("supports"):
                        continue
                    candidate = self._build_candidate(
                        provider=source.name,
                        framework=framework,
                        change_name=change_name,
                        change_desc=change_desc,
                        verdict=verdict,
                        release_title=summary.get("title", "release"),
                    )
                    self.candidates.append(candidate)
                    produced.append(candidate)

        return produced

    def _extract_summary(self, provider: str, body: str) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You are extracting LLM provider release information.",
                user=extract_release_summary_prompt(provider=provider, html_body=body),
                caller_label=f"s4.summary[{provider}]",
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("S4 summary extraction failed for %s: %s", provider, e)
            return None

    def _check_framework(
        self, framework: str, change_name: str, change_description: str
    ) -> dict[str, Any] | None:
        try:
            resp = self.llm.complete(
                system="You are checking whether a framework supports a new LLM provider feature.",
                user=framework_check_prompt(
                    framework=framework,
                    change_name=change_name,
                    change_description=change_description,
                ),
                caller_label=f"s4.check[{framework}/{change_name}]",
            )
            return parse_json_block(resp.text)
        except Exception as e:
            log.warning("S4 framework check failed for %s/%s: %s", framework, change_name, e)
            return None

    def _build_candidate(
        self,
        *,
        provider: str,
        framework: str,
        change_name: str,
        change_desc: str,
        verdict: dict[str, Any],
        release_title: str,
    ) -> Candidate:
        return Candidate(
            id=f"s4-{uuid.uuid4().hex[:12]}",
            discovered_at=datetime.now(tz=timezone.utc),
            strategy=self.name,
            target_repo=framework,
            category="feature",
            title=f"Add {provider} {change_name} support to {framework}",
            description=(
                f"Provider {provider} shipped: {release_title}.\n\n"
                f"New capability: {change_name} — {change_desc}\n\n"
                f"Framework verdict: {verdict.get('reasoning', '')} "
                f"(confidence {float(verdict.get('confidence', 0.0)):.2f})\n\n"
                f"Time-sensitive: provider just released, merge race window is short."
            ),
            suggested_action=(
                f"Open an issue in {framework} proposing support for {provider}'s {change_name}. "
                f"If maintainers are receptive, follow with a PR."
            ),
            evidence_urls=[
                next(
                    (s.url for s in PROVIDER_SOURCES if s.name == provider),
                    "",
                ),
            ],
            evidence_snippets=[],
            confidence=float(verdict.get("confidence", 0.5)),
            novelty=0.6,
            actionability=1.0,
            strategy_reputation=0.5,
            status="new",
        )
