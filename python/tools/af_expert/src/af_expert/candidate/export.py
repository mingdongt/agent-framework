from __future__ import annotations

from af_expert.candidate.model import Candidate


def render_candidate_spec(c: Candidate) -> str:
    lines: list[str] = []
    lines.append(f"# Candidate {c.id}")
    lines.append("")
    lines.append(f"**Repo:** {c.target_repo}")
    lines.append(f"**Strategy:** {c.strategy}")
    lines.append(f"**Category:** {c.category}")
    lines.append(f"**Confidence:** {c.confidence:.2f}")
    lines.append(f"**Discovered:** {c.discovered_at.isoformat()}")
    lines.append(f"**Title:** {c.title}")
    lines.append("")
    lines.append("## Description")
    lines.append(c.description)
    lines.append("")
    if c.target_files:
        lines.append("## Target")
        for path in c.target_files:
            lines.append(f"- `{path}`")
        lines.append("")
    if c.evidence_urls or c.evidence_snippets:
        lines.append("## Evidence")
        for url in c.evidence_urls:
            lines.append(f"- {url}")
        for snip in c.evidence_snippets:
            lines.append("```")
            lines.append(snip)
            lines.append("```")
        lines.append("")
    lines.append("## Suggested action")
    lines.append(c.suggested_action)
    lines.append("")
    if c.notes:
        lines.append("## Operator notes")
        lines.append(c.notes)
        lines.append("")
    return "\n".join(lines)
