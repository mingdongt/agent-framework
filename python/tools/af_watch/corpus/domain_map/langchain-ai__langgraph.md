# langchain-ai/langgraph — Domain Map
Last refreshed: 2026-05-18 (initial draft by claude-sonnet, needs operator review)

## Architecture in 5 sentences

- The core primitive is `StateGraph`: a builder that wires typed nodes (pure functions
  `State -> Partial[State]`) and edges into a directed graph, then compiles to an
  executable `CompiledStateGraph` via `.compile()`.
- State is a user-defined `TypedDict`; individual keys may be annotated with reducer
  functions (e.g. `Annotated[list, operator.add]`) so concurrent node writes are merged
  rather than overwritten — reducers are the concurrency contract.
- At runtime the engine follows the **Pregel superstep model** (inspired by Google Pregel
  / Apache Beam): all nodes scheduled for the current step fire in parallel, outputs are
  applied via reducers, then the next frontier is determined from conditional edges.
- Persistence is handled by a pluggable **Checkpointer** (SQLite, PostgreSQL, Redis,
  in-memory); every superstep is snapshotted, giving durable execution — agents survive
  process crashes and resume exactly where they left off.
- Human-in-the-loop is a first-class feature: a node raises `Interrupt(value)` to surface
  data to the caller and pause execution; the graph resumes later via
  `Command(resume=...)`, with the full `StateSnapshot` available for inspection or editing
  between steps.

## Key design choices (taste, not docs)

- **Declarative graph over imperative chains**: you describe *what connects to what*,
  not *how to sequence calls* — the engine owns the execution loop.
- **Reducers as the concurrency contract**: no locks; annotate state keys with merge
  functions and the framework guarantees reducer-safe fan-in from parallel branches.
- **`Send` API for dynamic fan-out**: a node can return `Send("node_name", custom_state)`
  to spawn N parallel subgraph invocations (map-reduce) without pre-declaring edges —
  the graph topology is not fully static.
- **`Command` as an escape hatch**: nodes return a `Command` object to both update state
  *and* redirect control flow in one return, collapsing what would otherwise need a
  separate routing node + conditional edge.
- **Subgraph composition**: a compiled graph is a valid node inside a parent graph;
  `Command(graph="parent", ...)` lets a subgraph bubble values up, enabling layered
  multi-agent architectures without bespoke wiring.
- **Seven streaming modes** (`values`, `updates`, `messages`, `checkpoints`, `tasks`,
  `custom`, `debug`) give callers fine-grained control; `StreamPart` is a discriminated
  union typed by the `type` field.
- **Node-level policies**: `RetryPolicy`, `CachePolicy`, `TimeoutPolicy` (wall-clock +
  idle), and `error_handler` are configured *per node* at graph-build time, not at
  invocation time — the graph is self-describing.
- **`context_schema`** (separate from `state_schema`) exposes immutable runtime data
  (e.g. DB connections, config) to all nodes without polluting the serializable state
  that checkpointers must persist across restarts.

## Current pain points
*(sourced from open issues + recently merged PRs, ~last 30 days)*

- **Long tool calls silently re-execute on resume** (issue #7417): operations taking
  ~180 s+ get replayed from checkpoint because granularity is per-superstep, not
  per-tool-call — a production foot-gun with expensive or non-idempotent tools.
- **SQLite vs PostgreSQL checkpoint divergence** (issue #7843): SQLite does not normalize
  channel values the way PostgreSQL does; teams that develop on SQLite and deploy on
  Postgres hit subtle state bugs that are invisible in local testing.
- **Sync loop incorrectly caches INTERRUPT/ERROR writes** (issue #7589): a bug in the
  synchronous execution path causes interrupt and error channel writes to be cached and
  re-applied on the next step, silently corrupting state.
- **`invoke(version='v2')` return-type surprise** (issue #7796): when
  `stream_mode != 'values'`, `invoke` returns `list[StreamPart]` instead of
  `GraphOutput` — undocumented, breaking callers that rely on the output schema.
- **Type-checker friction**: `add_messages` rejects valid `list[BaseMessage]` inputs
  (issue #6207); the `Annotated` reducer pattern produces types that mypy/pyright cannot
  fully validate without custom plugins or type-ignore suppressions.

## Unique advantages

- TODO (operator review)

## Deltas vs LangChain / ADK / pydantic-ai

- TODO (operator review)
