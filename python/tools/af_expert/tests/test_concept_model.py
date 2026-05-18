from __future__ import annotations

from datetime import datetime, timezone

import pytest

from af_expert.concept.model import Concept, ConceptImplementation


def test_implementation_minimal() -> None:
    impl = ConceptImplementation(
        repo="microsoft/agent-framework",
        files=["python/packages/core/agent_framework/_mcp.py"],
        functions=["_refresh_token"],
    )
    assert impl.repo == "microsoft/agent-framework"
    assert impl.compliant is None


def test_concept_minimal() -> None:
    c = Concept(
        id="mcp.oauth.refresh",
        description="MCP OAuth refresh-token grant handling",
        spec_ref="RFC 8707 §2.2",
    )
    assert c.id == "mcp.oauth.refresh"
    assert c.implementations == {}


def test_concept_id_kebab_validation() -> None:
    with pytest.raises(ValueError):
        Concept(id="MCP.OAuth.Refresh", description="...", spec_ref="...")


def test_concept_roundtrip_json() -> None:
    impl = ConceptImplementation(
        repo="microsoft/agent-framework",
        files=["x.py"],
        functions=["f"],
        last_modified="2026-05-14",
        compliant=True,
    )
    c = Concept(
        id="mcp.oauth.refresh",
        description="MCP OAuth refresh-token grant handling",
        spec_ref="RFC 8707",
        implementations={"microsoft/agent-framework": impl},
    )
    raw = c.model_dump_json()
    c2 = Concept.model_validate_json(raw)
    assert c2 == c
