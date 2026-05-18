from __future__ import annotations

from typing import Any

from af_expert.spec_corpus.base import PropertyResult, SpecProperty


class ToolResultFormatProperty(SpecProperty):
    spec = "mcp"
    name = "tool_result_format"
    description = "MCP tool_result must have `content` list and `isError` bool"

    def run(self, adapter: Any) -> PropertyResult:
        result = adapter.simulate_mcp_tool_result({
            "tool_name": "test_tool",
            "output": "hello",
        })
        payload = result.get("payload") or {}
        missing: list[str] = []
        if not isinstance(payload.get("content"), list):
            missing.append("content (must be list)")
        if not isinstance(payload.get("isError"), bool):
            missing.append("isError (must be bool)")
        if missing:
            return PropertyResult(
                passed=False,
                message=f"tool_result payload missing or malformed fields: {', '.join(missing)}",
                repro_snippet=(
                    "adapter.simulate_mcp_tool_result({'tool_name': 'test_tool', 'output': 'hello'})\n"
                    f"# returned payload: {payload!r}"
                ),
            )
        return PropertyResult(passed=True, message="tool_result payload format correct")
