from __future__ import annotations

from typing import Any

from af_expert.spec_corpus.base import PropertyResult, SpecProperty


class OAuthRefreshNoResourceProperty(SpecProperty):
    spec = "mcp"
    name = "oauth_refresh_no_resource"
    description = (
        "OAuth refresh-token request must NOT include `resource` parameter "
        "(RFC 8707 §2.2; Entra v2.0 rejects requests that do)"
    )

    def run(self, adapter: Any) -> PropertyResult:
        result = adapter.simulate_mcp_oauth_refresh_request({
            "grant_type": "refresh_token",
            "refresh_token": "test-token",
        })
        request = result.get("request") or {}
        if "resource" in request:
            return PropertyResult(
                passed=False,
                message=f"refresh request included 'resource' parameter: {request.get('resource')!r}",
                repro_snippet=(
                    "adapter.simulate_mcp_oauth_refresh_request({\n"
                    "    'grant_type': 'refresh_token', 'refresh_token': 'test-token'\n"
                    "})\n"
                    f"# returned request: {request!r}"
                ),
            )
        return PropertyResult(
            passed=True,
            message="refresh request correctly omits 'resource' parameter",
        )
