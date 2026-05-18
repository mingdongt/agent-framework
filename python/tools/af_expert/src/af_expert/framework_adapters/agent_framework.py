from __future__ import annotations

from typing import Any

from af_expert.framework_adapters.base import FrameworkAdapter


class AgentFrameworkAdapter(FrameworkAdapter):
    """Adapter for microsoft/agent-framework.

    Wave 5: stub implementation that returns compliant responses for all three
    MCP properties. Replacing the stubs with real calls into agent-framework's
    code (e.g., the actual MCP client and OAuth helpers) is follow-up work.
    """

    framework = "microsoft/agent-framework"

    def __init__(self) -> None:
        super().__init__()
        self._initialized = False

    def simulate_mcp_initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._initialized:
            return {"accepted": False, "reason": "already initialized"}
        self._initialized = True
        return {"accepted": True}

    def simulate_mcp_oauth_refresh_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Compliant: NO `resource` parameter on refresh-token grants
        return {
            "request": {
                "grant_type": "refresh_token",
                "refresh_token": payload.get("refresh_token", ""),
            }
        }

    def simulate_mcp_tool_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "payload": {
                "content": [{"type": "text", "text": str(payload.get("output", ""))}],
                "isError": False,
            }
        }
