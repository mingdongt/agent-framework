from __future__ import annotations

from pathlib import Path

from af_expert.concept.model import Concept, ConceptImplementation
from af_expert.concept.store import ConceptGraphStore


def test_empty_store_returns_empty_list(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    assert list(s.list_all()) == []


def test_add_and_get_concept(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    c = Concept(id="mcp.oauth.refresh", description="...", spec_ref="RFC 8707")
    s.upsert(c)

    fetched = s.get("mcp.oauth.refresh")
    assert fetched is not None
    assert fetched.id == "mcp.oauth.refresh"


def test_upsert_updates_existing(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    c = Concept(id="mcp.oauth.refresh", description="v1", spec_ref="RFC 8707")
    s.upsert(c)
    c2 = Concept(id="mcp.oauth.refresh", description="v2-updated", spec_ref="RFC 8707")
    s.upsert(c2)

    fetched = s.get("mcp.oauth.refresh")
    assert fetched.description == "v2-updated"


def test_store_persists_to_disk(tmp_state_dir: Path) -> None:
    s1 = ConceptGraphStore()
    s1.upsert(Concept(id="x.y", description="...", spec_ref=""))

    s2 = ConceptGraphStore()
    assert s2.get("x.y") is not None


def test_add_implementation(tmp_state_dir: Path) -> None:
    s = ConceptGraphStore()
    s.upsert(Concept(id="mcp.oauth.refresh", description="...", spec_ref=""))

    impl = ConceptImplementation(
        repo="microsoft/agent-framework",
        files=["x.py"],
        functions=["f"],
    )
    s.attach_implementation("mcp.oauth.refresh", impl)

    fetched = s.get("mcp.oauth.refresh")
    assert "microsoft/agent-framework" in fetched.implementations


def test_attach_implementation_missing_concept_raises(tmp_state_dir: Path) -> None:
    import pytest
    s = ConceptGraphStore()
    impl = ConceptImplementation(repo="x/y", files=[], functions=[])
    with pytest.raises(KeyError):
        s.attach_implementation("nonexistent", impl)
