# langchain-ai/langchain — Domain Map
Last refreshed: 2026-05-18 (initial draft by claude-sonnet, needs operator review)

## Architecture in 5 sentences

- LangChain is a layered monorepo: `langchain-core` owns the `Runnable` protocol and abstract base types;
  `langchain` adds higher-level chains, agents, and retrieval abstractions; `langchain-community` houses the
  long tail of third-party integrations; partner packages (`langchain-openai`, `langchain-anthropic`, etc.)
  encapsulate first-tier providers with maintained ownership.
- The central abstraction is `Runnable[Input, Output]`: every composable unit — prompts, models, output
  parsers, retrievers, tools — exposes `invoke / batch / stream / ainvoke / astream`, which lets any piece
  compose with any other via LCEL's `|` pipe operator without adapter glue.
- Agents are thin wrappers over a `(messages → model → tool-call decision → tool execution)` loop; since
  v0.2 the preferred implementation delegates orchestration to LangGraph, leaving `langchain` agent helpers
  as convenience constructors over LangGraph `CompiledGraph` objects.
- Memory and state are out-of-scope for `langchain` proper — handled either by manually accumulating the
  `messages` list or by LangGraph's persistent checkpointers; the core package makes no durability promises.
- Tool argument schemas are Pydantic models auto-generated from Python type annotations, but the `Runnable`
  machinery is not generically typed in a way mypy/pyright enforces end-to-end — type safety is
  runtime-first throughout.

## Package layout (navigational)

| Package | Role |
|---|---|
| `langchain-core` | `Runnable` protocol, `BaseChatModel`, `BaseMessage`, `BaseRetriever`, base tool types |
| `langchain` | Chains, agents (`create_react_agent`), retrieval, text-splitters, output parsers |
| `langchain-community` | 200+ best-effort integrations: vector stores, document loaders, tools |
| `langchain-openai` | First-party OpenAI + Azure OpenAI with maintained ownership |
| `langchain-anthropic` | First-party Anthropic with maintained ownership |
| `langchain-text-splitters` | Extracted text-splitting utilities |
| `langgraph` | Separate repo — the actual execution engine for agents since v0.2 |
| `langsmith` | Separate SaaS — the default observability layer |

## Key design choices (taste, not docs)

- **Runnable as the universal unit of composition, not a base class hierarchy.**
  Any callable wrapped in `RunnableLambda` becomes chainable. The `|` operator (`__or__`) builds
  `RunnableSequence` without requiring inheritance, which is why you can pipe a raw Python function between
  a prompt template and a chat model. The downside: `Runnable[Input, Output]` type parameters are mostly
  decorative — the real contract is duck-typed, not enforced by the type checker.

- **LCEL trades debuggability for composability.**
  `prompt | model | parser` is terse and streaming-transparent — every `|` step automatically propagates
  `astream()` tokens. The cost is that errors mid-chain surface as deeply nested `RunnableSequence`
  tracebacks. Without LangSmith, diagnosing which step failed and with what input requires manual
  `RunnableLambda` instrumentation.

- **Integration breadth is the product moat.**
  100+ chat model providers, vector stores, document loaders, and retrievers are first-class citizens.
  The breadth makes LangChain the "batteries-included" choice for new projects. The maintenance cost is
  visible: provider-specific edge cases (Mistral's missing `strict` param, Ollama multimodal newline bug,
  Fireworks `ContextOverflowError`) accumulate faster than any single team can address them.

- **`with_structured_output()` abstracts function-calling vs. json_schema routing.**
  It accepts a Pydantic model or JSON schema and routes to the appropriate provider mechanism automatically.
  This is genuinely useful for multi-provider codebases. It leaks when provider-specific options (e.g.,
  OpenAI `strict`, Mistral `response_format`) aren't surfaced, and silently conflicts with `bind_tools()`.

- **Observability is opt-in via LangSmith, not baked into the execution model.**
  `LANGCHAIN_TRACING_V2=true` + an API key activates full chain tracing. This keeps the core library free
  of SaaS coupling for teams that don't want it, but means the default debugging experience — plain Python
  exceptions with no chain context — is significantly worse than frameworks with first-party tracing.

- **Community/partner split is a deliberate quality tiering.**
  Partner packages (`langchain-openai`, `langchain-anthropic`) are maintained by the provider or LangChain
  team. Community packages are best-effort pull-request driven. The split is the right architectural call,
  but API surface consistency varies sharply; users cannot assume a `community` integration matches the
  capabilities of a partner one.

- **LangGraph is the real orchestration engine; `langchain` agents are now sugar.**
  `create_react_agent()` returns a LangGraph `CompiledGraph`. The `langchain` package is migrating toward
  a pure component library while LangGraph owns agent execution. This is architecturally sound but
  confusing: the README still leads with agents as a `langchain` feature, not a LangGraph one.

- **No built-in persistence — intentional boundary.**
  Unlike ADK (session service) or pydantic-ai (message history accumulation), LangChain delegates
  persistence entirely to LangGraph checkpointers or user-managed stores. The boundary is philosophically
  correct for a component library but means every production deployment reinvents the persistence wheel.

## Current pain points

- **`with_structured_output()` silently conflicts with `bind_tools()`.**
  Calling both on the same model drops whichever binding came first, with no warning (issue #35320).
  No merge logic or guard exists. This is the most user-hostile footgun for tool-augmented structured-
  output agents, and it's been open since at least late 2024.

- **Streaming drops response metadata.**
  `ChatOpenAI.with_structured_output(..., method="json_schema").stream()` silently discards
  `response_metadata` including `x-request-id` and `usage` (issues #37452, #37435). Cost accounting
  and request tracing are impossible mid-stream. Active fix attempts around `additional_kwargs`
  preservation are incomplete as of May 2026.

- **Provider error handling is per-integration, not protocol-level.**
  `ContextOverflowError` was added independently for Fireworks (PR #37458) and OpenAI (PR #37457) in
  the same week. There is no `ContextWindowError` base class in `langchain-core` — cross-provider
  error handling requires catching provider-specific exception types, defeating the abstraction goal.

- **Heavy imports on `BaseChatModel` cold-start.**
  `transformers` is imported unconditionally at module load for some model integrations, adding ~2–4s
  cold-start overhead in pure-API deployments (open issue). Disproportionately affects Lambda and
  serverless contexts where the library is most attractive as a thin integration layer.

- **Windows portability gaps accumulate silently.**
  `read_text()` encoding defaults and `grep_search` fallbacks break on Windows for valid UTF-8 files
  (issue #37438). The OSS contributor base skews Mac/Linux; Windows bugs sit open longer and
  aggregate into a meaningful compatibility gap for enterprise Windows-first shops.

## Unique advantages
- TODO (operator review needed)

## Deltas vs LangGraph / ADK / pydantic-ai

- TODO (operator review needed)
- Suggested angle 1: LangChain has by far the deepest integration catalog (200+ community + partner
  packages). ADK and pydantic-ai have far fewer integrations and require LiteLLM or custom adapters
  to reach the same provider breadth.
- Suggested angle 2: pydantic-ai enforces output types at static analysis time via `Agent[Deps, Output]`
  generics; LangChain's `Runnable[Input, Output]` generics are decorative. Teams with large typed Python
  codebases will feel the difference.
- Suggested angle 3: ADK ships in-framework evaluation (rubric-based LLM-as-judge, trajectory comparison);
  LangChain relies entirely on LangSmith SaaS for this. This matters for air-gapped or on-prem deployments.
- Suggested angle 4: LangGraph (LangChain's orchestration layer) is a more expressive graph-DAG model than
  ADK's `SequentialAgent`/`ParallelAgent` but requires more explicit wiring. ADK orchestration is simpler
  to reason about for linear flows; LangGraph is more powerful for non-linear conditional ones.
- Suggested angle 5: LangChain has no first-party persistence primitive; ADK has `SessionService` backends
  (in-memory, DB, Vertex AI); pydantic-ai leaves it to user code. LangGraph checkpointers are the closest
  equivalent but are a separate dependency.
