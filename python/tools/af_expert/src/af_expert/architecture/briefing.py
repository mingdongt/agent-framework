from __future__ import annotations

import logging
from datetime import datetime, timezone

from af_expert.architecture.scanner import FileInventory
from af_expert.llm import LLM


log = logging.getLogger(__name__)


def build_briefing_prompt(*, repo: str, inventory: FileInventory) -> str:
    parts: list[str] = []
    parts.append(
        f"You will produce an architecture briefing for the OSS repository '{repo}'.\n"
        "The briefing should be a concise markdown document for an engineer who wants\n"
        "to understand the repo's shape without reading the code. Use these sections:\n\n"
        "## Purpose\n## Top-level components\n## Key abstractions\n## Provider integrations\n## Notable subsystems\n\n"
        "Be specific about file paths. Do not invent details — if uncertain, say so.\n"
    )
    parts.append(f"\nREPO: {repo}\n")

    if inventory.readme_excerpt:
        parts.append("\n### README excerpt\n")
        parts.append(inventory.readme_excerpt)
        parts.append("\n")

    parts.append("\n### Source files (truncated)\n")
    for f in inventory.source_files[:200]:
        parts.append(f"- {f}\n")

    if inventory.provider_files:
        parts.append("\n### Provider integration files\n")
        for provider, files in inventory.provider_files.items():
            parts.append(f"- **{provider}**: {', '.join(files[:5])}\n")

    if inventory.pyproject_present:
        parts.append("\n(Python project: pyproject.toml present)\n")
    if inventory.package_json_present:
        parts.append("\n(JS/TS project: package.json present)\n")

    return "".join(parts)


def render_briefing(*, repo: str, inventory: FileInventory, llm: LLM) -> str:
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    header = f"# {repo}\n\n*Briefing generated at {timestamp}*\n\n"

    try:
        prompt = build_briefing_prompt(repo=repo, inventory=inventory)
        resp = llm.complete(
            system=(
                "You are a senior engineer summarizing an OSS repository's architecture. "
                "Be concise, accurate, and cite file paths."
            ),
            user=prompt,
            caller_label=f"architecture.briefing[{repo}]",
            max_tokens=2000,
        )
        body = resp.text
    except Exception as e:
        log.warning("Briefing generation failed for %s: %s", repo, e)
        body = (
            "**Briefing could not be generated** (LLM error).\n\n"
            "## Fallback inventory\n\n"
            f"- Source files: {len(inventory.source_files)}\n"
            f"- Test files: {len(inventory.test_files)}\n"
            f"- Providers detected: {', '.join(inventory.provider_files.keys()) or 'none'}\n"
        )

    return header + body + "\n"
