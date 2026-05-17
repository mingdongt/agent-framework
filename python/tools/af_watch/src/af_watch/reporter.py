# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path

from af_watch.models import BriefingData, Opportunity, OpportunityType

_TYPE_EMOJI = {
    OpportunityType.BUG_FIX: "🐛",
    OpportunityType.BUG_PORT: "🪞",
    OpportunityType.FEATURE_PARITY: "🧩",
    OpportunityType.INDUSTRY_ADAPT: "⚡",
    OpportunityType.DESIGN_BORROW: "🏗️",
    OpportunityType.DOCS_SAMPLE: "📖",
    OpportunityType.DRIFT_DECISION: "🤔",
}


class Reporter:
    def __init__(self, *, reports_root: Path) -> None:
        self._root = reports_root

    def write(self, data: BriefingData) -> Path:
        window_dir = self._root / data.window_end.strftime("%Y-%m-%d")
        window_dir.mkdir(parents=True, exist_ok=True)
        deep_dir = window_dir / "deep_dives"
        deep_dir.mkdir(exist_ok=True)

        briefing = self._render_briefing(data)
        briefing_path = window_dir / "briefing.md"
        briefing_path.write_text(briefing, encoding="utf-8")

        jsonl_lines = [opp.model_dump_json() for opp in data.opportunities]
        (window_dir / "opportunities.jsonl").write_text("\n".join(jsonl_lines), encoding="utf-8")

        for opp in data.opportunities:
            opp_dir = deep_dir / opp.id
            opp_dir.mkdir(exist_ok=True)
            (opp_dir / "analysis.md").write_text(self._render_deep_dive(opp), encoding="utf-8")

        return briefing_path

    def _render_briefing(self, data: BriefingData) -> str:
        date = data.window_end.strftime("%Y-%m-%d")
        top3 = data.opportunities[:3]
        rest = data.opportunities[3:]

        lines = [f"# Weekly Briefing — {date}", ""]
        lines.append("## Top opportunities this week")
        for i, opp in enumerate(top3, start=1):
            emoji = _TYPE_EMOJI.get(opp.type, "•")
            lines.append(
                f"{i}. **{opp.target}** {emoji} _{opp.type.value}_ "
                f"[{opp.risk}/{opp.effort}] — {opp.rationale}"
            )
            lines.append(f"   → deep_dives/{opp.id}/analysis.md")
        lines.append("")

        if data.industry_highlights:
            lines.append("## Industry context")
            for entry in data.industry_highlights:
                ts = entry.timestamp.strftime("%Y-%m-%d")
                lines.append(f"- **{ts}** — {entry.title}: {entry.summary} ({entry.url})")
            lines.append("")

        if rest:
            lines.append("## Additional opportunities")
            for opp in rest:
                emoji = _TYPE_EMOJI.get(opp.type, "•")
                lines.append(
                    f"- {emoji} `{opp.id}` [{opp.risk}/{opp.effort}] {opp.target} — {opp.rationale}"
                )
            lines.append("")

        if data.activity_summary:
            lines.append("## Activity (raw, last 7 days)")
            for repo, count in sorted(data.activity_summary.items(), key=lambda kv: -kv[1]):
                lines.append(f"- {repo}: {count} merged PRs")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _render_deep_dive(self, opp: Opportunity) -> str:
        emoji = _TYPE_EMOJI.get(opp.type, "•")
        lines = [
            f"# {opp.id}: {emoji} {opp.type.value}",
            "",
            "## Five slots",
            f"- **Target:** {opp.target}",
            f"- **Action:** {opp.action}",
            f"- **Evidence:** {opp.evidence}",
            f"- **Effort:** {opp.effort}",
            f"- **Risk:** {opp.risk} ({opp.risk_rationale})",
            "",
            "## Rationale",
            opp.rationale,
            "",
            f"**Tier:** {opp.tier}",
            f"**Repro status:** {opp.repro_status}",
        ]
        if opp.supporting_personas:
            lines.append(f"**Supporting personas:** {', '.join(opp.supporting_personas)}")
        if opp.repro_artifact:
            lines.append(f"**Repro artifact:** `{opp.repro_artifact}`")
        if opp.handoff_command:
            lines.append("")
            lines.append("## How to act")
            lines.append(f"```bash\n{opp.handoff_command}\n```")
        return "\n".join(lines) + "\n"
