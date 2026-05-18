from __future__ import annotations

from typing import Any

from af_expert.spec_corpus.mcp import (
    MCP_PROPERTIES,
    DuplicateInitializeProperty,
    OAuthRefreshNoResourceProperty,
    ToolResultFormatProperty,
)


class _CompliantAdapter:
    framework = "fake/compliant"
    def __init__(self) -> None:
        self.initialize_count = 0

    def simulate_mcp_initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.initialize_count += 1
        return {"accepted": self.initialize_count == 1}

    def simulate_mcp_oauth_refresh_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"request": {"grant_type": "refresh_token", "refresh_token": "x"}}

    def simulate_mcp_tool_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"payload": {"content": [{"type": "text", "text": "hello"}], "isError": False}}


class _NonCompliantAdapter:
    framework = "fake/buggy"
    def simulate_mcp_initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"accepted": True}  # always accepts → violates duplicate rule

    def simulate_mcp_oauth_refresh_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"request": {"grant_type": "refresh_token", "resource": "https://api/"}}

    def simulate_mcp_tool_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"payload": {"content": "not a list", "isError": "not a bool"}}


def test_mcp_properties_count() -> None:
    assert len(MCP_PROPERTIES) == 3


def test_compliant_adapter_passes_all() -> None:
    adapter = _CompliantAdapter()
    for prop in MCP_PROPERTIES:
        r = prop.run(adapter=adapter)
        assert r.passed, f"{prop.full_id} should pass on compliant adapter: {r.message}"


def test_non_compliant_adapter_fails_all() -> None:
    adapter = _NonCompliantAdapter()
    for prop in MCP_PROPERTIES:
        r = prop.run(adapter=adapter)
        assert not r.passed, f"{prop.full_id} should fail on buggy adapter"
        assert r.repro_snippet, f"{prop.full_id} should provide a repro_snippet on failure"


def test_property_full_id_format() -> None:
    assert DuplicateInitializeProperty().full_id == "mcp/duplicate_initialize_rejected"
    assert OAuthRefreshNoResourceProperty().full_id == "mcp/oauth_refresh_no_resource"
    assert ToolResultFormatProperty().full_id == "mcp/tool_result_format"
