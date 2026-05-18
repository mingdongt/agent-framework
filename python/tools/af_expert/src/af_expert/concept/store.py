from __future__ import annotations

import json
from pathlib import Path

from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.config import _state_dir
from af_expert.state import atomic_write


class ConceptGraphStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path else _state_dir() / "concept_graph.json"

    def _load(self) -> dict[str, Concept]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            cid: Concept.model_validate(cdata)
            for cid, cdata in raw.get("concepts", {}).items()
        }

    def _save(self, concepts: dict[str, Concept]) -> None:
        payload = {
            "version": 1,
            "concepts": {cid: c.model_dump() for cid, c in concepts.items()},
        }
        atomic_write(self.path, json.dumps(payload, indent=2, sort_keys=True, default=str))

    def list_all(self) -> list[Concept]:
        return list(self._load().values())

    def get(self, concept_id: str) -> Concept | None:
        return self._load().get(concept_id)

    def upsert(self, concept: Concept) -> None:
        concepts = self._load()
        concepts[concept.id] = concept
        self._save(concepts)

    def attach_implementation(
        self, concept_id: str, impl: ConceptImplementation
    ) -> None:
        concepts = self._load()
        if concept_id not in concepts:
            raise KeyError(f"Concept {concept_id!r} not in store")
        concepts[concept_id].implementations[impl.repo] = impl
        self._save(concepts)

    def remove(self, concept_id: str) -> bool:
        concepts = self._load()
        if concept_id not in concepts:
            return False
        del concepts[concept_id]
        self._save(concepts)
        return True
