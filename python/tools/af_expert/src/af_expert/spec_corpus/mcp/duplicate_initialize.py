from __future__ import annotations

from typing import Any

from af_expert.spec_corpus.base import PropertyResult, SpecProperty


class DuplicateInitializeProperty(SpecProperty):
    spec = "mcp"
    name = "duplicate_initialize_rejected"
    description = "MCP server must reject duplicate `initialize` requests after the first"

    def run(self, adapter: Any) -> PropertyResult:
        # First initialize should succeed
        first = adapter.simulate_mcp_initialize({"client_info": {"name": "test"}})
        if not first.get("accepted"):
            return PropertyResult(
                passed=False,
                message="first initialize was not accepted (precondition failed)",
                repro_snippet=(
                    "adapter.simulate_mcp_initialize({'client_info': {'name': 'test'}})\n"
                    f"# returned: {first!r}"
                ),
            )
        # Second initialize MUST be rejected
        second = adapter.simulate_mcp_initialize({"client_info": {"name": "test"}})
        if second.get("accepted"):
            return PropertyResult(
                passed=False,
                message="duplicate initialize was accepted; spec requires rejection",
                repro_snippet=(
                    "adapter.simulate_mcp_initialize({'client_info': {'name': 'test'}})  # first\n"
                    "adapter.simulate_mcp_initialize({'client_info': {'name': 'test'}})  # second\n"
                    f"# second returned: {second!r}"
                ),
            )
        return PropertyResult(passed=True, message="duplicate initialize correctly rejected")
