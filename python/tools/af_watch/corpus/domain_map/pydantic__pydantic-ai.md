# pydantic/pydantic-ai — Domain Map
Last refreshed: 2026-05-18 (initial draft by claude-sonnet, needs operator review)

## Architecture in 5 sentences

pydantic-ai centres on a single generic `Agent[DepsType, OutputType]` class that drives a
request-response loop: prompt → model call → optional tool-execution retries → validated
structured output. Dependencies are threaded through every dynamic function via a typed
`RunContext[DepsType]` context object, so the framework enforces at static-check time that
callers pass the right dependency shape — not just at runtime. Tools are registered with
`@agent.tool` decorators; their parameter schemas are auto-generated from type annotations,
and any validation failure triggers a `ModelRetry` back to the model against a configurable
per-tool and global retry budget. Structured outputs are validated by Pydantic models;
streaming (`run_stream`) prioritises first-match delivery and deliberately leaves dangling
tool calls unexecuted. The `pydantic_graph` sub-package adds an explicit state-machine layer
for orchestration complexity that exceeds what tool-based delegation handles cleanly.

## Key design choices (taste, not docs)

- **Type parameters are load-bearing, not decorative.** `Agent[MyDeps, MyResult]` means
  mypy/pyright catches wrong dep shapes and wrong output models at write-time. This is the
  defining aesthetic difference from LangChain-style frameworks, where type errors surface
  as runtime `KeyError` or silent coercion.

- **DI over globals.** There is no thread-local context or ambient registry. Everything the
  agent can touch — DB connections, HTTP clients, feature flags — must be declared upfront
  and flows through `RunContext`. Tests become trivial: pass a fake deps object, no mocking.

- **Static instructions get prompt-cached; dynamic ones do not.** Boilerplate system content
  sits in the static slot (Anthropic/OpenAI cache-eligible); per-request context stays
  dynamic and outside cache boundaries. This is an explicit cache-budget design decision.

- **Capabilities as composable YAML units.** Tools + hooks + instructions + model settings
  bundle into `Capability` objects loadable from YAML/JSON without code changes — the
  framework's answer to "how do you ship a reusable agent component."

- **Logfire is first-class, not an afterthought.** `logfire.instrument_pydantic_ai()` yields
  span-level traces for every model call, tool invocation, and retry with zero manual
  instrumentation. Logfire cost tracking appears in the same trace as business logic spans.

- **`pydantic_graph` is the explicit escape hatch.** Rather than hiding state-machine
  complexity behind opaque orchestration abstractions, pydantic-ai surfaces it as a separate,
  typed graph primitive. Teams graduate to it only when delegation/handoff patterns break down.

- **Streaming stops at first valid output.** `run_stream()` resolves the moment it matches
  the declared output type, even if tool calls are still in-flight — a conscious UX tradeoff
  that prioritises low-latency first tokens but bites teams assuming full execution.

- **Agents are stateless by design.** The framework discourages storing state inside agent
  objects; long-lived state belongs in dependencies or message history passed explicitly per
  run. This makes horizontal scaling and testing straightforward at the cost of more
  boilerplate for stateful workflows.

## Current pain points

- **Uneven provider coverage.** Provider-specific knobs (Gemini `top_k`, Bedrock
  `additionalModelRequestFields`, Bedrock adaptive thinking for Claude Sonnet 4.6 / Opus 4.6)
  require per-provider workarounds or are missing entirely. The model-agnostic abstraction
  leaks whenever a model's differentiating feature sits outside the common parameter envelope.

- **No built-in message persistence.** The framework manages in-memory message history but
  offers no pluggable persistence layer. An open issue since December 2024 — teams building
  production deployments bolt on their own store and wire `message_history` manually each run.

- **Cost tracking breaks across heterogeneous models.** Mixing models in a single run makes
  monetary cost calculation impossible from `result.usage` alone. Token counts aggregate
  correctly; dollar figures do not. The docs call this out explicitly as a known limitation.

- **Custom/self-hosted OpenAI-compatible providers lack a `base_url` field in `AgentSpec`.**
  Teams running local models or proxy gateways must construct provider objects manually
  rather than via a simple config field.

- **Mid-conversation system prompt rendering is broken for Anthropic/Google** when
  `message_history` is present — a confirmed open bug affecting agents that inject dynamic
  context partway through a conversation.

- **v2 API migration limbo.** `Agent.to_a2a()`, `stream_responses()`, and the `instrument=`
  param are deprecated in the v2 cycle. Teams that adopted the beta API are in a
  deprecation-not-breaking-change window that extends "which API generation am I on?"
  confusion without forcing a clean cut.

- **`pydantic_graph` only recently left beta.** The graph API graduated in recent PRs;
  documentation and community patterns around it are still thin relative to the core agent
  API. Teams choosing graph-based orchestration are early adopters.

## Unique advantages
- TODO (operator review)

## Deltas vs LangChain / ADK / pydantic-ai
- TODO (operator review)
