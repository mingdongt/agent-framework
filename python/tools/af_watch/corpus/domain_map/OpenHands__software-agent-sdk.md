# OpenHands/software-agent-sdk — Domain Map
Last refreshed: 2026-05-18 (seed)

## Architecture in 5 sentences

The SDK is a four-package Python monorepo (`openhands-sdk`, `openhands-agent-server`, `openhands-tools`, `openhands-workspace`) where the core primitive is an `Agent` bound to an `LLM` and a `Conversation` that mediates every tool call against a workspace. The flagship agent is `CodeActAgent`, which emits executable code actions rather than structured JSON tool calls, allowing the LLM to express multi-step plans as runnable Python/shell code that the `DockerRuntime` sandboxes and evaluates in a containerised environment. A pluggable runtime abstraction sits between the agent and the host OS — implementations include `DockerRuntime` (ephemeral per-conversation containers), a Kubernetes variant, and a bare-metal local mode — so the same `Conversation` API works on a laptop or in cloud batch. A controller loop inside the `Conversation` class drives the agentic cycle (observe → think → act → observe), routing LLM responses to tool executors and feeding observations back until a `TaskDone` or budget-limit signals termination. A condenser component prunes and summarises the message history before each LLM call, keeping context within token budgets while preserving actionable observations.

## Key design choices (taste, not docs)

- **Code-as-action over JSON tool calls**: `CodeActAgent` lets the LLM write raw code rather than rigid tool schemas; this sacrifices structural predictability for expressiveness and is the primary reason for the 77.6 SWE-bench score.
- **LiteLLM as the LLM shim**: all model calls pass through LiteLLM, making provider switching (OpenAI, Anthropic, Gemini, DeepSeek, local) a one-line config change and enabling per-profile token-caching headers with no agent code changes.
- **Skills marketplace instead of built-in hardcoding**: `OpenHands/extensions` supplies optional workspace-level skills (e.g., uv, deno) that are injected based on repo markers, keeping the core SDK small and letting downstream users extend without forking.
- **Conversation forking as a first-class primitive**: v1.21+ treats branch-and-retry as a core workflow, not a workaround; callers can fork a `Conversation` at any checkpoint and explore alternative action sequences without re-running from scratch.
- **Client-server by default for production**: the `openhands-agent-server` REST/WebSocket layer is the assumed deployment model for anything beyond a script, enabling multi-tenant scheduling, secrets encryption at rest, and cloud-proxy forwarding.
- **MCP (Model Context Protocol) as tool-extension layer**: recent work adds a `/api/mcp/test` endpoint and encrypted env-var injection, treating MCP as the standard interface for third-party tool integrations.

## Current pain points (last 30 days, from PR / issue clustering)

- **Model compatibility fragility**: new LLM releases (DeepSeek v4-pro/flash, Kimi K2.6, Gemini 3.1) routinely break because prompt-cache markers and token-count assumptions are model-specific; issues like #3267 appear within days of model launches.
- **MCP secret expansion**: `MCP tool parameters do not expand secrets/environment variables` (#3277) is an open customer-support bug indicating the encryption/expansion pipeline has gaps when tools are invoked via MCP bridges.
- **Agent discovery and session resume**: issue #3236 flags that ACP session listing and resume lack a stable agent-discovery endpoint, creating friction for multi-agent orchestration scenarios.
- **Non-blocking subagent execution is stale**: #2047 (`feat(delegate): Non-blocking background subagent execution`) has been open and stale for months — parallel/async delegation is a known capability gap relative to frameworks like LangGraph.
- **Windows support is nascent**: the PowerShell terminal backend was only added in v1.22; Windows-specific edge cases are not yet systematically tested.
- **`max_budget_per_task` not enforced**: #1337 (stale) — cost-capping per task is requested but unimplemented, making cloud deployments require external budget enforcement.

## Unique advantages

- **SWE-bench 77.6**: best-in-class verified score on the canonical software-engineering agentic benchmark; directly tied to the CodeActAgent + DockerRuntime combination.
- **Sandboxed runtime abstraction**: the clean `Runtime` interface (Docker / Kubernetes / local) is production-grade, with security posture (two-phase `rm` detection, credential redaction, cipher encryption of MCP secrets) that most SDK-level frameworks do not offer.
- **Velocity**: 1,675+ commits, v1.22.1 in ~1 year; the team ships multiple PRs per day including breaking API changes with migration paths.
- **Conversation forking**: branching at an arbitrary conversation checkpoint is architecturally clean and not found in pydantic-ai or the Google ADK at this maturity level.
- **Extensions marketplace**: declarative skill injection via repo-marker detection is a practical DX win that sidesteps the "how do I teach the agent about my stack" problem.

## Deltas vs LangChain / ADK / pydantic-ai

| Dimension | OpenHands SDK | LangChain | Google ADK | pydantic-ai |
|---|---|---|---|---|
| Primary abstraction | `Conversation` + `CodeActAgent` + `Runtime` | `Chain` / `AgentExecutor` / `LangGraph` | `Agent` + `Runner` + `Session` | `Agent` + typed `Tool` + `RunContext` |
| Action model | Code-as-action (runnable Python/shell) | JSON tool calls | JSON function calls | Validated Pydantic tool schemas |
| Sandbox/runtime | First-class Docker/K8s runtime | None (user-managed) | None (Cloud Run optional) | None |
| LLM shim | LiteLLM (any provider, one config) | Many integrations, heavy | Gemini-first, others via LiteLLM | Any via `models` param |
| Context management | Built-in condenser | Manual or LangChain memory | Session service | `MessageHistory` limit param |
| Multi-agent | Subagent delegation (async gap) | LangGraph graphs | Multi-agent via `AgentTool` | Not primary focus |
| Conversation forking | Yes (v1.21+) | No | No | No |
| Benchmark validation | SWE-bench 77.6 | No official score | No official score | No official score |
| Deployment target | SDK + REST server + Cloud | SDK + LangServe | SDK + Agent Engine (GCP) | SDK only |
| MCP support | Yes (encrypted, test endpoint) | Partial | Partial | Partial |
