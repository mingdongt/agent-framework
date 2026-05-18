# strands-agents/sdk-python — Domain Map
Last refreshed: 2026-05-18 (seed)

## Architecture in 5 sentences

The SDK's execution unit is `Agent`: a model bound to a system prompt, a
`ToolRegistry`, a `ConversationManager`, optional `plugins`, and an event
`hooks` bus — configured entirely through constructor arguments, with Amazon
Bedrock (`BedrockModel` + Claude 4 Sonnet) as the out-of-the-box default.
`Agent.__call__()` (or `invoke_async` / `stream_async`) drives an async event
loop whose inner cycle calls the model, dispatches tool calls via a pluggable
`ToolExecutor`, and recurses until the model emits `end_turn`, making the loop
explicitly recursive rather than iterative.  Multi-agent topology is expressed
at three levels of abstraction: `agent.as_tool()` for ad-hoc delegation,
`Swarm` for self-organising handoff-driven teams that share a `SharedContext`
working memory, and `Graph` for statically declared DAGs with conditional edges
and parallel batch execution.  A2A (Agent-to-Agent) protocol support — with a
full task lifecycle state machine and a `server.py` / `executor.py` pair —
gives the SDK a standards-compliant inter-agent wire protocol on top of the
Python-native patterns.  The hook system (`BeforeInvocationEvent`,
`AfterInvocationEvent`, `BeforeModelCallEvent`, `AfterModelCallEvent`) is the
primary extensibility seam, with `plugins` (e.g., `MultiAgentPlugin`) layering
higher-level orchestration features without modifying core classes.

## Key design choices (taste, not docs)

- **Bedrock-first, provider-agnostic in practice.**  The default model is
  `BedrockModel` (Claude 4 Sonnet in us-west-2); AWS credentials are required
  out of the box.  But the `model=` parameter accepts any of 13+ providers
  (Anthropic, Gemini, OpenAI, Ollama, LiteLLM, etc.), so the AWS dependency is
  a default, not a hard constraint.  This is an honest reflection of AWS/Bedrock
  sponsorship rather than an architectural limit.

- **Recursive event loop, not an iterative scheduler.**  `event_loop_cycle()`
  calls itself via `recurse_event_loop()` after tool results are appended.
  This keeps the flow simple (each cycle is self-contained) but means call-stack
  depth grows with tool-use turns; it is different from frameworks that use
  explicit while-loops with shared state.

- **Tools are first-class citizens with multiple ingestion formats.**  The
  `ToolRegistry` accepts Python callables decorated with `@tool`, module paths,
  directory paths (hot-reloadable), dict specs, or entire `ToolProvider`
  objects — including `MCPClient` wrappers.  MCP tools are indistinguishable
  from native tools at the execution layer.

- **Three distinct multi-agent primitives.**  Rather than a single abstraction,
  Strands offers `agent.as_tool()` (delegation), `Swarm` (autonomous handoffs
  with shared memory), and `Graph` (declared topology with conditional routing).
  These compose: a `Swarm` can be a node inside a `Graph`.

- **Hooks over middleware.**  The hooks system uses typed event objects and
  supports `resume` semantics — an `AfterInvocationEvent` handler can inject new
  input and continue the loop — enabling checkpoint / human-in-the-loop patterns
  without a dedicated interrupt API.

- **Structured output is a first-class parameter.**  Both `Agent.__init__` and
  individual call sites accept a `structured_output_model` (Pydantic model);
  the event loop has a dedicated extraction path that terminates the cycle once
  the model produces a conforming object.

- **Conversation and session management are separate concerns.**  `ConversationManager`
  (sliding window, null) handles in-memory context trimming; `SessionManager`
  handles persistence across invocations.  Splitting these lets stateless and
  stateful deployments share the same agent code.

- **Bidirectional streaming is in `experimental/`.**  The `BidiAgent` supports
  real-time audio/voice via Amazon Nova Sonic, Google Gemini Live, and OpenAI
  Realtime API.  It is explicitly not stable API, signaling maturity distinction
  from the main surface.

## Current pain points (last 30 days, from PR / issue clustering)

- **`repository_session_manager` injects orphaned `toolResult` blocks.**  When
  tool calls are interrupted or abandoned, the session manager inserts incorrect
  toolResult blocks into the conversation history, corrupting subsequent turns
  (issue #2296, open).

- **No `max_iterations` cap on the agent loop.**  The event loop recurses until
  `end_turn` or an exception; there is no built-in guard against runaway
  recursion.  Issue #2298 requests an explicit cap.  Until then, long agentic
  runs risk deep call stacks or unbounded cost.

- **Swarm telemetry is broken.**  OpenTelemetry context detachment fails inside
  Swarm orchestration (`"Failed to detach context"` error), requiring a hot-fix
  (PR #2281).  BidiAgent telemetry is entirely absent (issue #2300).

- **Bedrock token counting is unreliable.**  Three consecutive PRs (#2249, #2250,
  #2254) patched Bedrock context-window lookup and token counting in a short
  window, suggesting the Bedrock integration still has sharp edges around
  token budget management.

- **Hook callback ordering is inconsistent.**  `After*` event hooks fire in
  reverse registration order (issue #2282), which surprises users composing
  multiple plugins.  A v2 cleanup is planned but not yet merged.

- **boto3 client re-initialised on every call.**  `S3SessionManager` creates a
  new boto3 client per invocation, causing latency and connection churn at scale
  (issue #1163, open since Nov 2025).

- **Monorepo migration pending.**  Issue #2286 signals an upcoming consolidation
  of `sdk-python`, `tools`, and related repos into a single monorepo, which will
  likely change import paths and versioning in the near term.

## Unique advantages

- **Native A2A protocol implementation.**  Strands ships a complete A2A task
  lifecycle state machine (`executor.py`, `server.py`, `_converters.py`) inside
  the core package — one of the first agent SDKs to treat A2A as built-in
  rather than an external adapter.

- **Composable multi-agent primitives that nest.**  `Swarm` and `Graph` both
  implement `MultiAgentBase`, so a swarm can be a graph node or vice versa.
  This composability is rare; most frameworks force a single orchestration model.

- **MCP is a zero-ceremony first-class integration.**  `MCPClient` is a
  `ToolProvider`; adding an MCP server is one constructor call with no special
  event loop plumbing.

- **Hot-reloadable tools from a directory.**  `load_tools_from_directory=True`
  lets agents pick up new tool files without restart — useful for iterative
  development and long-running server deployments.

- **Hook-based `resume` semantics.**  `AfterInvocationEvent` handlers can
  re-enter the agent loop with new input, enabling human-in-the-loop and
  approval gates without breaking the async streaming contract.

- **OpenTelemetry ambient tracing.**  Every model call, tool dispatch, and agent
  invocation emits spans without user instrumentation code; compatible with any
  OTLP backend.

- **Sandbox abstraction in progress.**  PR #2198 adds a `Sandbox` core
  abstraction for isolated execution environments, signaling intent to support
  long-horizon coding tasks similar to OpenAI's SandboxAgent.

## Deltas vs LangChain / ADK / openai-agents-python / pydantic-ai

| Dimension | strands-agents | openai-agents-python | Google ADK | pydantic-ai |
|---|---|---|---|---|
| Execution model | Recursive async event loop | Runner loop + Responses API | Event-driven graph | Type-safe tool dispatch |
| Default provider | Amazon Bedrock (Claude) | OpenAI | Google Gemini | Any (no default) |
| Multi-agent topology | Delegation + Swarm + Graph (composable) | Handoff objects + agent-as-tool | Hierarchical agents + events | Not a primary concern |
| A2A protocol | Native (built-in server + executor) | None built-in | None built-in | None |
| MCP support | First-class ToolProvider | First-class peer tool | Tool adapter | Plugin |
| Guardrails | Hooks (BeforeInvocation, AfterInvocation) | First-class abort-capable | No built-in concept | Validators on result type |
| Tracing | Ambient OTel | Ambient, hosted viewer | Cloud Trace | None built-in |
| Structured output | Pydantic model parameter | `output_type` Pydantic | Pydantic via config | Native, deepest support |
| Session / memory | ConversationManager + SessionManager (separate) | Pluggable; SQLite + Redis | In-memory + managed | No built-in |
| Voice / realtime | BidiAgent (experimental) | `gpt-realtime-2` module | None | None |
| Sandbox | In progress (PR #2198) | SandboxAgent (stable) | Code Execution tool | None |
| Footprint | Medium (AWS SDK optional) | Minimal core + opt-ins | Medium | Minimal |

**Key delta:** Strands is the most AWS-native option with the deepest A2A
support and the richest multi-agent primitive set (three composable patterns).
Its main bet is that Bedrock + A2A standards-compliance beats both OpenAI-lock-in
(openai-agents-python) and GCP-lock-in (ADK), at the cost of an AWS-shaped
default configuration that requires credential setup before a first `hello world`.
