# microsoft/agent-framework — Domain Map
Last refreshed: 2026-05-18 (initial draft by claude, needs operator review)

## Architecture in 5 sentences
- **Dual-language SDK**, .NET and Python, with independent first-class implementations — not a wrapper. Mirrored package names (`agent-framework-*` Python ↔ `Microsoft.Agents.AI.*` .NET).
- **Provider-keyed package layout**: each LLM/runtime gets its own package (`openai`, `anthropic`, `claude`, `gemini`, `bedrock`, `ollama`, `foundry`, `foundry_local`) — explicitly avoids lowest-common-denominator abstraction.
- **Three orthogonal runtimes**: in-process agents (`core`), durable orchestration (`durabletask`), and distributed/multi-agent (`orchestrations`, `a2a`).
- **Protocols are first-class packages**: `a2a` (Agent-to-Agent), `ag-ui` (human-facing streaming), Skills (file-based `SKILL.md`), MCP via provider plugins.
- **Microsoft ecosystem deeply integrated**: `foundry` / `foundry_hosting` / `foundry_local`, `copilotstudio`, `github_copilot`, `purview`, `azure-ai-search`, `azure-cosmos`, `azurefunctions`, `chatkit` — Microsoft productizations rather than generic abstractions.

## Key design choices (taste, not docs)
- **Imperative async Workflow, not declarative graph (LangGraph)** — preserves Python control flow; `declarative` package exists but is a YAML-driven overlay, not the default.
- **Don't flatten provider differences** — Anthropic `thinking`, Gemini grounding metadata, OpenAI Responses `reasoning_summary` survive through dedicated provider packages.
- **Skills as a file-based primitive** (`SKILL.md` frontmatter, YAML scalars) with strict reject of path-traversal — independent of MCP, lives alongside it. Recent: list[str] arguments for file-based skill scripts (breaking change).
- **Magentic + Handoff + GroupChat + Sequential + Concurrent** as first-class orchestration patterns shipped in `orchestrations`. Magentic specifically (Microsoft Research) — active E2E workflow coverage being added.
- **DevUI shipped in-box** (`devui`, `Aspire.Hosting.AgentFramework.DevUI`) — uncommon among competitors. Recent breaking changes here; users hitting AG-UI session lifecycle issues.
- **Hyperlight + isolation_key** for hosted-memory-agent runtime — true sandboxing as a first-class concern, not just Docker.
- **`ContextProvider` + `SkillsProvider`** abstractions for cross-cutting agent context. Recent pain point: providers not always propagated to all agent types (GitHubCopilotAgent #5876 fix, FoundryAgent #5883 outstanding).
- **AG-UI moved from preview → release candidate** in recent weeks — protocol stabilizing; .NET fix for tool result message-id collisions; naming for handoff workflows.

## Current pain points (last ~30 days, from PR cluster + open issues)
- **MCP tool result events silently dropped** (#5897) — model fabricates errors. High-impact, active.
- **AG-UI session stops updating after first turn** (#5898) + tool result message-id collisions (.NET fix landed) — protocol replay edges still being shaken out.
- **Telemetry data shape**: agent responses showing as user messages (#5804); sensitive-data telemetry config gap (#5873).
- **ContextProvider / SkillsProvider not always propagated**: GitHubCopilotAgent missing tools added via ContextProvider (recent fix); FoundryAgent ignores SkillsProvider in context_providers (#5883).
- **Declarative outputSchema YAML bug** (#5888) — declarative agent YAML produces incorrect output.
- **DevUI session lifecycle** — multiple recent breaking changes; "Add edit, regenerate, rerun support" (#5891) implies the dev loop UX is being iterated rapidly.
- **MCP discovery scale** — progressive MCP discovery/dispatch mode requested for large MCP servers (#5821); current impl loads all upfront.
- **Magentic / Handoff workflow polish** — naming, route builder, edge tests all churning recently.

## Unique advantages
- **Dual-language parity** with real round-trip tests — no other major framework runs both .NET and Python at this depth (ADK Python-only, LangChain Python-leading, pydantic-ai Python-only, OpenAI Python-leading). This is genuinely unique.
- **AG-UI** is the only mainstream human-streaming protocol from a major framework. Competitors either don't have one or use raw SSE chunks.
- **Microsoft ecosystem productizations** (Foundry / Foundry Local / Copilot Studio / Purview) are not just adapters — they're hosted-runtime, declarative-workflow, compliance-integrated paths that competitors can't replicate.
- **In-box DevUI + Hyperlight isolation** — agent dev/test/sandbox tooling shipped with the framework.
- **A2A protocol as first-class** — Microsoft is one of the protocol's early movers; first-class implementation. Note: strands-agents now also ships a full A2A server lifecycle, so this is becoming a 2-horse race rather than uniquely Microsoft.
- TODO (operator: confirm Hyperlight is genuinely differentiated; ADK/openai-agents-python may have something comparable for sandbox)

## Deltas vs LangChain / ADK / pydantic-ai
- **vs LangChain / LangGraph**: imperative async vs declarative graph. agent-framework's `declarative` package is a YAML overlay, not the default — opposite of LangGraph's stance. LangGraph has `Send` API for dynamic topology; agent-framework's `orchestrations` has named patterns (Magentic, GroupChat) instead.
- **vs google/adk-python**: agent-framework is provider-pluralist (every provider its own package); ADK is Gemini-first with LiteLLM for the rest. agent-framework has no LiteLLM dependency in core paths.
- **vs pydantic/pydantic-ai**: pydantic-ai pushes type-safety as the primary abstraction (Pydantic models everywhere, ctx.deps dependency injection); agent-framework treats type-safety as one concern among many.
- **vs openai/openai-agents-python**: openai-agents is Responses-API-first with handoffs + guardrails + SandboxAgent as primitives; agent-framework has handoffs as one of several patterns, has Hyperlight for isolation, and ships its own Foundry deployment story. openai-agents has server-side Responses compaction (`OpenAIResponsesCompactionSession`) — agent-framework's compaction strategy is TODO to confirm.
- **vs OpenHands/software-agent-sdk**: OpenHands is a coding-agent SDK with `CodeActAgent` generating runnable code instead of JSON tool calls — fundamentally different abstraction. agent-framework targets general agents, not coding specifically.
- **vs strands-agents/sdk-python**: both first-class A2A; strands uses recursive event loop (call-stack-bound), agent-framework's workflow is non-recursive.
- TODO (operator: dotnet-side comparison — most competitors are Python-only so .NET is a unique-axis rather than a delta. Worth calling out as positioning, not gap.)

## Hot subsystems to watch (next 4 weeks)
- AG-UI replay / session lifecycle (RC stabilizing)
- MCP scale (progressive discovery, tool result event reliability)
- DevUI dev loop ergonomics
- Declarative workflow YAML correctness
- ContextProvider / SkillsProvider propagation completeness across agent types
- Foundry Hosted Agents (RAG, Skills, Memory samples landing)
