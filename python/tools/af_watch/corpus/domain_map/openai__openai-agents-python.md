# openai/openai-agents-python — Domain Map
Last refreshed: 2026-05-18 (seed)

## Architecture in 5 sentences

The SDK's execution unit is `Agent`: an LLM bound to instructions, a tool list,
guardrails, and optional handoff targets — all plain Python dataclasses, no
subclassing required.  `Runner.run()` drives a synchronous or async loop that
calls the Responses API, dispatches tool calls, fires guardrail checks, and
follows handoffs until the agent emits a final text response.  Handoffs are
first-class: an agent can transfer control to another agent either as a
structured "handoff" object (the receiving agent gets full context) or as an
ordinary tool call, giving callers two explicit topological primitives (chain vs
delegation).  Tracing is ambient — every span (LLM call, tool dispatch, handoff,
guardrail pass) is recorded automatically and exposed through a hosted trace
viewer plus a `TracingProcessor` extension point.  Optional layers (Sessions for
conversation history, SandboxAgent for containerised workspaces, Realtime for
voice via `gpt-realtime-2`) are isolated behind optional dependency groups so the
core package stays minimal.

## Key design choices (taste, not docs)

- **Responses-API-first.**  The SDK treats the Responses API as the canonical
  backend; Chat Completions is a supported fallback, but new features (server-
  side tool hosting, response compaction) are Responses-API-only.  This is a
  deliberate commitment to OpenAI's newer surface at the cost of
  non-OpenAI portability for those features.

- **Guardrails are synchronous gates, not post-hoc filters.**  Input guardrails
  run before the LLM call; output guardrails run before the result is returned.
  They can raise `GuardrailTripwireTriggered` to abort the entire run.  This
  makes safety checks a first-class execution concern rather than middleware.

- **No orchestrator class.**  There is no `Orchestrator`, `Pipeline`, or
  `Graph` object; topology lives inside the agents themselves (via the
  `handoffs` list).  This keeps small workflows simple but makes complex
  multi-agent graphs harder to reason about statically.

- **Structured outputs via Pydantic.**  `output_type` on an `Agent` can be any
  Pydantic model; the SDK wraps it into a JSON schema tool call so the model
  always returns a validated object rather than freeform text.

- **Sessions as a pluggable storage contract.**  `OpenAIConversationsSession`,
  `OpenAIResponsesCompactionSession`, and `AdvancedSQLiteSession` all share one
  interface; Redis / Valkey providers are community-extensible.  The default is
  stateless (no session), which avoids hidden state surprises in simple scripts.

- **MCP as a peer tool protocol.**  MCP tool servers are treated identically to
  native Python function tools at the scheduling layer, making the SDK a natural
  host for heterogeneous tool ecosystems.

- **Lifecycle hooks are sparse by design.**  The main extension points are
  `RunHooks` (on_tool_start, on_tool_end, on_handoff, on_agent_start/end) and
  the tracing processor.  There is no plugin bus or middleware stack; the surface
  is kept intentionally small.

## Current pain points (last 30 days, from PR / issue clustering)

- **Session data-consistency bugs.**  `AdvancedSQLiteSession.add_items` can
  report success after a metadata write failure; `delete_branch()` leaves orphan
  messages in the base table.  Both are open.

- **Realtime tool errors are silent to the model.**  When a realtime-mode tool
  throws an exception or times out, no model-visible error output is sent back,
  so the model cannot recover gracefully.

- **Pre/post-execution validation gaps.**  Several open issues request a stable
  hook for pre-execution tool-call validation and a tamper-evident post-execution
  accountability layer.  `FunctionTool` does not expose the underlying Python
  callable as a stable public attribute.

- **Agent state between turns is awkward.**  State that needs to persist across
  turns but is not conversation history (e.g., counters, flags) has no canonical
  home; users work around it with context objects or session hacks.

- **Schema mutation side-effects.**  Recent fixes (v0.17.x) patched cases where
  tool JSON schemas were mutated in-place, causing subtle bugs when agents were
  reused across multiple runs.

## Unique advantages

- **Zero-config tracing.**  Tracing is on by default; every run produces a
  structured trace without any instrumentation code.  The hosted viewer requires
  an OpenAI account but the processor protocol supports third-party sinks
  (Langfuse, Braintrust, etc.) out of the box.

- **SandboxAgent for long-horizon tasks.**  Containerised workspaces with
  filesystem state, git-repo mounting, and port access give the SDK a credible
  story for multi-step coding / research tasks that exceed single-context limits.

- **Responses API compaction.**  `OpenAIResponsesCompactionSession` can
  summarise long conversation histories server-side, keeping token costs bounded
  without client-side summarisation logic.

- **Voice is a first-class module, not a demo.**  The optional `[voice]` group
  wires directly into `gpt-realtime-2`; Twilio integration exists (with known
  bugs, see pain points), positioning it for production telephony.

- **Provider-agnostic at the model layer.**  `MultiProvider` and `LiteLLM`
  integration allow any OPENAI-compatible endpoint; the framework is not
  structurally tied to OpenAI billing even though Responses API features are.

## Deltas vs LangChain / ADK / pydantic-ai

| Dimension | openai-agents-python | LangChain | Google ADK | pydantic-ai |
|---|---|---|---|---|
| Execution model | Runner loop + Responses API | Chain / LCEL graph | Event-driven graph | Type-safe tool dispatch |
| Multi-agent topology | Handoff objects + agent-as-tool | Agent executors, custom routing | Hierarchical agents + events | Not a primary concern |
| Guardrails | First-class, abort-capable | Callback / output parsers | No built-in concept | Validators on result type |
| Tracing | Ambient, built-in viewer | LangSmith (paid) | Cloud Trace | None built-in |
| Structured output | `output_type` Pydantic model | Output parsers (fragile) | Pydantic via config | Native, deepest support |
| Sandbox / long-horizon | SandboxAgent (v0.14+) | None | Code Execution tool | None |
| Session / memory | Pluggable; SQLite + Redis | Many backends, complex | In-memory + managed | No built-in |
| Voice | `gpt-realtime-2` module | None built-in | None built-in | None |
| Footprint | Minimal core + opt-ins | Very large | Medium | Minimal |

**Key delta:** openai-agents-python occupies a middle ground — heavier than
pydantic-ai (which is purely type-driven) but far lighter than LangChain.
Its main bet is that Responses API + ambient tracing beats DIY observability, a
bet that only pays if users stay on OpenAI infrastructure for the opinionated
features.
