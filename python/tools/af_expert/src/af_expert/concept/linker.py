from __future__ import annotations

import logging
from datetime import datetime, timezone

from af_expert.architecture.scanner import FileInventory
from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.llm import LLM, parse_json_block


log = logging.getLogger(__name__)


def build_linker_prompt(*, repo: str, concept: Concept, inventory: FileInventory) -> str:
    parts: list[str] = []
    parts.append(
        f"You are linking the domain concept '{concept.id}' to its implementation in "
        f"the repository '{repo}'.\n\n"
        f"Concept description: {concept.description}\n"
        f"Spec reference: {concept.spec_ref or 'none'}\n\n"
        "Below is the repository's source file inventory. Identify which files (and "
        "which top-level functions/classes within them) implement this concept. If the "
        "concept is not present, set matches=false.\n\n"
        "Respond with ONLY a fenced ```json block with fields:\n"
        "- matches: true | false\n"
        "- files: list of file paths from the inventory\n"
        "- functions: list of function/class names\n"
        "- confidence: float 0.0-1.0\n\n"
    )
    parts.append("### Source files\n")
    for f in inventory.source_files[:300]:
        parts.append(f"- {f}\n")
    if inventory.provider_files:
        parts.append("\n### Provider files\n")
        for provider, files in inventory.provider_files.items():
            parts.append(f"- {provider}: {', '.join(files[:5])}\n")
    return "".join(parts)


def link_concept_to_repo(
    *, repo: str, concept: Concept, inventory: FileInventory, llm: LLM
) -> ConceptImplementation | None:
    try:
        resp = llm.complete(
            system="You are linking an OSS architectural concept to its implementation in a repo.",
            user=build_linker_prompt(repo=repo, concept=concept, inventory=inventory),
            caller_label=f"concept.linker[{concept.id}->{repo}]",
        )
        data = parse_json_block(resp.text)
    except Exception as e:
        log.warning("concept.linker failed for %s -> %s: %s", concept.id, repo, e)
        return None

    if not data.get("matches"):
        return None

    return ConceptImplementation(
        repo=repo,
        files=list(data.get("files", [])),
        functions=list(data.get("functions", [])),
        last_modified=datetime.now(tz=timezone.utc).date().isoformat(),
    )
