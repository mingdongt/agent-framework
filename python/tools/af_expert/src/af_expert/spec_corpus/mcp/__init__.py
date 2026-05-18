from __future__ import annotations

from af_expert.spec_corpus.mcp.duplicate_initialize import DuplicateInitializeProperty
from af_expert.spec_corpus.mcp.oauth_refresh_no_resource import OAuthRefreshNoResourceProperty
from af_expert.spec_corpus.mcp.tool_result_format import ToolResultFormatProperty


MCP_PROPERTIES = [
    DuplicateInitializeProperty(),
    OAuthRefreshNoResourceProperty(),
    ToolResultFormatProperty(),
]
