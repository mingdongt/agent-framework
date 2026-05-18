from __future__ import annotations

from af_expert.concept.model import Concept
from af_expert.concept.store import ConceptGraphStore


SEED_CONCEPTS: list[Concept] = [
    # MCP
    Concept(id="mcp.transport.streamable_http",
            description="MCP transport over HTTP+SSE with streaming response support",
            spec_ref="MCP spec 1.x streamable-http transport",
            tags=["mcp", "transport"]),
    Concept(id="mcp.oauth.refresh",
            description="MCP OAuth refresh-token grant; must not include resource per RFC 8707",
            spec_ref="RFC 8707 §2.2", tags=["mcp", "auth", "oauth"]),
    Concept(id="mcp.headers.redirect_safety",
            description="MCP header_provider headers must not be re-injected on cross-origin redirects",
            spec_ref="HTTP security; MCP design discussion",
            tags=["mcp", "transport", "security"]),
    Concept(id="mcp.duplicate_initialize",
            description="MCP server must reject duplicate initialize requests after first",
            spec_ref="MCP spec initialize lifecycle", tags=["mcp", "protocol"]),
    Concept(id="mcp.tool_result.format",
            description="MCP tool_result payload structure (content blocks, isError flag)",
            spec_ref="MCP spec tools", tags=["mcp", "tools"]),
    # Anthropic
    Concept(id="anthropic.thinking_blocks",
            description="Anthropic thinking blocks with signature; orphan signatures must be skipped",
            spec_ref="Anthropic extended thinking docs", tags=["anthropic", "streaming"]),
    Concept(id="anthropic.tool_use.cancellation",
            description="Anthropic tool_use cancellation mid-stream cleanup",
            spec_ref="Anthropic tool use API", tags=["anthropic", "tools", "streaming"]),
    Concept(id="anthropic.cache_control",
            description="Anthropic prompt caching via cache_control on content blocks",
            spec_ref="Anthropic prompt caching docs", tags=["anthropic", "caching"]),
    Concept(id="anthropic.tool_use.computer_use",
            description="Anthropic computer use beta tool with screenshot + action loop",
            spec_ref="Anthropic computer use docs", tags=["anthropic", "tools", "beta"]),
    Concept(id="anthropic.batch_api",
            description="Anthropic message batches API (asynchronous bulk inference)",
            spec_ref="Anthropic batches docs", tags=["anthropic", "batch"]),
    # OpenAI
    Concept(id="openai.responses_api",
            description="OpenAI Responses API (unified endpoint for chat + tools + structured outputs)",
            spec_ref="OpenAI API reference", tags=["openai"]),
    Concept(id="openai.structured_outputs",
            description="OpenAI structured outputs via response_format JSON schema",
            spec_ref="OpenAI structured outputs docs", tags=["openai", "schemas"]),
    Concept(id="openai.realtime_api",
            description="OpenAI Realtime API for low-latency voice/audio agents",
            spec_ref="OpenAI Realtime docs", tags=["openai", "voice"]),
    # Google / Gemini
    Concept(id="gemini.thinking_signatures",
            description="Gemini thinking_blocks with parallel thought_signatures field",
            spec_ref="LiteLLM / Gemini docs", tags=["google", "gemini", "streaming"]),
    Concept(id="gemini.live_api",
            description="Gemini Live API for streaming multimodal sessions with tool use",
            spec_ref="Gemini Live docs", tags=["google", "gemini"]),
    Concept(id="gemini.const_schemas",
            description="Gemini accepts const in JSON schemas; some frameworks drop it",
            spec_ref="Gemini structured outputs", tags=["google", "gemini", "schemas"]),
    # AG-UI
    Concept(id="agui.event_metadata",
            description="AG-UI protocol event metadata propagation across handoffs",
            spec_ref="AG-UI spec", tags=["agui", "protocol"]),
    Concept(id="agui.tool_history_replay",
            description="AG-UI tool history replay across sessions; must preserve message_id stability",
            spec_ref="AG-UI tool history docs", tags=["agui", "tools", "replay"]),
    # Tools
    Concept(id="tools.parallel_execution",
            description="Multiple tool calls in one assistant message; framework executes in parallel",
            spec_ref="Multiple provider docs", tags=["tools", "parallel"]),
    Concept(id="tools.cancellation_lifecycle",
            description="Tool execution can be cancelled mid-call; cleanup of resources + state required",
            spec_ref="Framework-specific", tags=["tools", "cancellation"]),
    # Async
    Concept(id="async.cancellation_propagation",
            description="asyncio.CancelledError propagation across LLM client + tool boundaries",
            spec_ref="Python asyncio docs", tags=["async", "python"]),
    Concept(id="async.contextvars.session_state",
            description="ContextVar-based session state isolation between concurrent requests",
            spec_ref="Python 3.7+ contextvars", tags=["async", "python", "state"]),
    # Tokens / Cost
    Concept(id="tokens.cache_hit_accounting",
            description="Provider-reported cache_read_input_tokens accounting for cost reporting",
            spec_ref="Anthropic + OpenAI usage fields", tags=["tokens", "cost"]),
    Concept(id="tokens.image_token_estimation",
            description="Image input token estimation per provider (different formulae)",
            spec_ref="Anthropic vision + OpenAI vision docs", tags=["tokens", "vision"]),
    # Memory
    Concept(id="memory.summarization_truncation",
            description="Conversation history summarization with deterministic truncation point",
            spec_ref="Multiple framework implementations", tags=["memory", "context"]),
    # Multi-agent
    Concept(id="handoff.context_passing",
            description="Multi-agent handoff: which context fields cross the boundary",
            spec_ref="OpenAI swarm + agent-framework Magentic", tags=["multi-agent", "handoff"]),
    # Schemas
    Concept(id="schema.pydantic_v1_v2",
            description="Pydantic v1 vs v2 compatibility shims in tool / output schemas",
            spec_ref="Pydantic migration docs", tags=["schemas", "pydantic"]),
    Concept(id="schema.tool_to_provider_mapping",
            description="Tool JSON schema -> provider-specific schema (Anthropic vs OpenAI vs Gemini)",
            spec_ref="Framework adapters", tags=["schemas", "tools"]),
    # Safety
    Concept(id="safety.prompt_injection_corpus",
            description="Known prompt-injection corpus; framework safety layer must catch or flag",
            spec_ref="OWASP LLM Top 10", tags=["safety", "security"]),
    # Streaming
    Concept(id="streaming.sse_reconnect",
            description="SSE reconnect logic: must not duplicate events on resume",
            spec_ref="HTTP SSE spec + Anthropic/OpenAI clients", tags=["streaming"]),
]


def seed_into(store: ConceptGraphStore) -> int:
    for c in SEED_CONCEPTS:
        store.upsert(c)
    return len(SEED_CONCEPTS)
