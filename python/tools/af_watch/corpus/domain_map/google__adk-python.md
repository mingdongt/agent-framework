# google/adk-python — Domain Map
Last refreshed: 2026-05-18 (initial draft by claude-sonnet, needs operator review)

## Architecture in 5 sentences

- The core reasoning unit is `LlmAgent` — a Python class combining a model reference, instruction string, tool list, and optional sub-agents; everything else in the framework is scaffolding around it.
- Workflow agents (`SequentialAgent`, `LoopAgent`, `ParallelAgent`) are pure orchestration shells that own no model and make no LLM calls themselves; they route execution to child `LlmAgent` instances, keeping orchestration deterministic and separately testable.
- Context is not a flat message list: the framework composes each model call from a structured assembly of session state, artifact references, memory retrieval results, and tool outputs — the `sessions`, `memory`, and `artifacts` subpackages each own a distinct slice of this assembly.
- Model access is bifurcated: Gemini gets a native first-party integration (Vertex AI SDK / Google AI SDK, including Live API audio/video streaming), while all other providers (Claude, Ollama, vLLM, LiteLLM-proxied endpoints) go through a LiteLLM adapter in the `models` package.
- Production deployment is GCP-opinionated: `Vertex AI Agent Engine` is the reference runtime, `Vertex AI Session Service` is the default session backend, and Cloud Run is the containerized deploy target — the "model-agnostic" claim is true, but the infrastructure story is built for Google Cloud.

## Package layout (navigational)

The `google.adk` namespace is decomposed into ~25 top-level subpackages. The load-bearing ones for understanding system behavior:

| Package | Role |
|---|---|
| `agents` | `LlmAgent`, `SequentialAgent`, `ParallelAgent`, `LoopAgent` |
| `models` | Gemini-native + LiteLLM adapter layer |
| `sessions` | `SessionService` implementations (in-memory, DB, Vertex AI) |
| `memory` | Optional semantic retrieval layer over session history |
| `tools` | Function tools, OpenAPI tools, MCP toolset, auth flows |
| `evaluation` | Rubric metrics, samplers, trajectory comparison |
| `a2a` | Agent-to-Agent JSON-RPC protocol for remote agents |
| `telemetry` | OpenTelemetry instrumentation (has contextvars leak bug, #5722) |
| `auth` + `integrations` | OAuth flows, Secret Manager credential injection |

## Key design choices (taste, not docs)

- **Gemini is first-class, everyone else is a plugin**: Live API multimodal streaming (audio, video, images), native function-calling, and grounding are only available on Gemini. LiteLLM-backed models inherit LiteLLM's capabilities, not ADK's. This is not a gap to be filled — it's an explicit product bet.
- **Workflow agents have no model by design**: You cannot add "light reasoning" at the orchestrator layer without promoting it to a full `LlmAgent`. The tradeoff is debuggability and predictability; the cost is that non-linear flows require manual wiring rather than LLM judgment at the routing node.
- **Code-first over config-driven**: Agent definitions are Python classes, not YAML manifests. Declarative registration exists but is secondary. This aligns with software engineering workflows (type checking, unit tests, version control diffs) at the cost of being inaccessible to non-engineers.
- **Sessions are first-class; memory is optional retrieval**: `SessionService` (in-memory, database, Vertex AI-backed) is the load-bearing state primitive. `MemoryService` is a separate, optional layer for semantic retrieval on top of session history — a cleaner separation than frameworks that conflate the two.
- **Evaluation ships in-framework**: The `evaluation` package provides rubric-based LLM-as-judge scoring, custom metric definitions, `LocalEvalSampler`, trajectory comparison, and a visual debugger. Most competing frameworks rely on external tooling (LangSmith, Braintrust) for this.
- **A2A protocol for cross-agent networking**: The `a2a` subpackage implements Google's Agent-to-Agent JSON-RPC protocol, enabling remote agent composition across process/service boundaries. It's a bet on a cross-vendor standard that is still pre-1.0 and not widely adopted outside Google tooling yet.
- **Auth and credential management are first-class surface area**: `auth` and `integrations.secret_manager` are top-level subpackages with tool-level OAuth flows, credential injection, and Secret Manager integration. This is load-bearing for enterprise tool integrations — but the implementation is visibly incomplete (see pain points).
- **Parallel v1/v2 tracks are intentional but create ecosystem friction**: `v1.x` (stable), `v2.0-alpha`, and `v2.0-beta` are all actively merged into as of May 2026. The `v2` branch appears to be a breaking-API rewrite with no published migration timeline, creating ambiguity for library consumers.

## Current pain points

- **Concurrency is an active reliability hole** (issues #5721, #5723, #5729 — all open as of 2026-05-18): `BaseToolset` caches prefixed tools keyed by a single invocation ID and breaks under concurrent multi-agent calls; `InMemorySessionService` allows duplicate event appends during concurrent broadcasts; `MCPToolset` throws `"Attempted to exit cancel scope"` errors in async multi-agent scenarios. These cluster around a single root cause: the async-safe shared-state design was not load-tested for concurrent multi-agent workloads.
- **Session event retrieval semantics are underspecified across backends** (#5730, #5131): `DatabaseSessionService.get_session` returns all events when `num_recent_events=0` instead of an empty set; Vertex AI Session Service `raw_event` storage behavior diverges from local behavior. Suggests session backends share an interface but not a contract test suite.
- **Evaluation metrics fail silently on edge-case inputs** (#5732, #5415, #5215): `rubric_based_final_response_quality_v1` returns `NOT_EVALUATED` on valid inputs with no error; `LocalEvalSampler` crashes on `None` metric scores; `expected_invocation` was not marked `Optional` in the eval schema despite being absent in many test cases. The eval system is recent and the edge-case surface is still being mapped.
- **OAuth / credential infrastructure is incomplete** (#5691, #3046): `credential_key` incorrectly includes `redirect_uri`, causing lookup misses across deployments; the OAuth `prompt` parameter is hardcoded and not configurable per-flow. Auth is load-bearing for any tool that requires user-scoped credentials, so these gaps surface quickly in production.
- **Agent Engine replays all session events on `_init_session`** (#5714): triggers `429 RESOURCE_EXHAUSTED` errors on sessions with long histories. This is a performance and reliability regression specific to the Vertex AI Agent Engine backend, affecting long-running production agents.

## Unique advantages

- TODO (operator: requires cross-framework comparison; suggested research angles below)
- Suggested angle 1: Live API multimodal streaming (audio/video tool calls mid-conversation) — appears to be structurally unavailable in LangChain, pydantic-ai, and most Python agent frameworks; requires direct Gemini integration.
- Suggested angle 2: In-framework evaluation depth (rubric-based LLM-as-judge + trajectory comparison + visual debugger) vs. external tooling dependency in LangChain / pydantic-ai.
- Suggested angle 3: A2A protocol — if it gains cross-vendor adoption, ADK has a head start on federated multi-agent architectures.
- Suggested angle 4: Vertex AI Agent Engine as a managed production runtime — no self-hosted orchestrator required; compare against LangGraph Platform (managed) or DIY FastAPI deploys.

## Deltas vs LangChain / pydantic-ai / CrewAI

- TODO (operator: requires hands-on cross-framework experience; suggested research angles below)
- Suggested angle 1: ADK `SequentialAgent` / `ParallelAgent` vs. LangGraph's DAG nodes — ADK orchestration is simpler to reason about but less expressive for non-linear flows that need conditional branching at every node.
- Suggested angle 2: pydantic-ai uses Pydantic model schemas as the agent's structured output contract; ADK uses instruction strings + Python class definitions. pydantic-ai is stricter about output types; ADK is more flexible for open-ended tool-calling agents.
- Suggested angle 3: LangChain memory is pluggable-but-flat (conversation buffer, summary, vector store); ADK separates session state (ordered event log) from memory retrieval (semantic search over past sessions) as distinct subsystems.
- Suggested angle 4: CrewAI is role-based with a team metaphor; ADK is capability-based with a hierarchy metaphor — different mental models for the same multi-agent problem.
- Suggested angle 5: LangChain has no first-party evaluation framework (relies on LangSmith SaaS); ADK ships evaluation in-library, which matters for air-gapped or on-prem deployments.
