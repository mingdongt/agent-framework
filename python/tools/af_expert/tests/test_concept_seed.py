from __future__ import annotations

from pathlib import Path

from af_expert.concept.seed import SEED_CONCEPTS, seed_into
from af_expert.concept.store import ConceptGraphStore


def test_seed_has_20_to_50_concepts() -> None:
    assert 20 <= len(SEED_CONCEPTS) <= 50


def test_seed_concepts_all_valid() -> None:
    for c in SEED_CONCEPTS:
        assert c.id
        assert c.description
        assert "." in c.id


def test_seed_into_idempotent(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    seed_into(s)
    n_first = len(s.list_all())

    seed_into(s)
    n_second = len(s.list_all())
    assert n_first == n_second
    assert n_first == len(SEED_CONCEPTS)


def test_seed_into_preserves_user_concepts(tmp_state_dir: Path) -> None:
    from af_expert.concept.model import Concept

    s = ConceptGraphStore()
    s.upsert(Concept(id="user.custom", description="my own", spec_ref=""))
    seed_into(s)

    assert s.get("user.custom") is not None
    assert len(s.list_all()) == len(SEED_CONCEPTS) + 1
