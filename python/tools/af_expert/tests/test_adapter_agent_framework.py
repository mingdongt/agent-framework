from __future__ import annotations

from af_expert.framework_adapters.agent_framework import AgentFrameworkAdapter


def test_adapter_has_framework_name() -> None:
    a = AgentFrameworkAdapter()
    assert a.framework == "microsoft/agent-framework"


def test_adapter_initialize_accepts_first_rejects_second() -> None:
    a = AgentFrameworkAdapter()
    r1 = a.simulate_mcp_initialize({"client_info": {"name": "t"}})
    r2 = a.simulate_mcp_initialize({"client_info": {"name": "t"}})
    assert r1.get("accepted") is True
    assert r2.get("accepted") is False


def test_adapter_oauth_refresh_omits_resource() -> None:
    a = AgentFrameworkAdapter()
    r = a.simulate_mcp_oauth_refresh_request({"grant_type": "refresh_token"})
    assert "resource" not in r.get("request", {})


def test_adapter_tool_result_has_valid_format() -> None:
    a = AgentFrameworkAdapter()
    r = a.simulate_mcp_tool_result({"tool_name": "x", "output": "y"})
    payload = r.get("payload", {})
    assert isinstance(payload.get("content"), list)
    assert isinstance(payload.get("isError"), bool)
