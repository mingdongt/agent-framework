# af-watch

Weekly expert-grade briefing of high-leverage contribution opportunities across the agent framework ecosystem, oriented around microsoft/agent-framework.

> Part of the **microsoft/agent-framework ecosystem-engineering initiative**
> — internal tooling supporting MAF (Microsoft's next-generation unified
> agent framework) through competitive ecosystem mapping, high-leverage
> opportunity identification, and accelerated contribution execution.
>
> Sibling tools: [af-expert](../af_expert/) (always-on intelligence pipeline) · [af-fix](../af_fix/) (issue → draft-PR executor)

## What it does

- **Scans 10 competing agent frameworks** (LangChain, LangGraph, ADK, pydantic-ai, openai-agents-python, OpenHands, DSPy, Phoenix, strands-agents, agent-framework itself) for recent activity, design shifts, and protocol changes.
- **Reasons over a hand-curated corpus** — per-framework opinionated domain maps + 15-feature comparison matrix + monthly industry intel — driven by 12 parallel LLM prompts (6 expert questions × 6 persona prompts) via the local `claude` CLI subprocess. No Anthropic API key needed; auth is taken from the operator's `claude` install.
- **Produces a weekly `briefing.md`** ranking 5–15 opportunities — each tagged by one of 7 types (🐛 bug-fix / 🪞 bug-port / 🧩 feature-parity / ⚡ industry-adapt / 🏗️ design-borrow / 📖 docs-sample / 🤔 drift-decision) — plus a per-opportunity `analysis.md` with evidence trail.
- **Designed for one human reviewer** to decide weekly investment in ~10 minutes.

## Quick start

```bash
cd python/tools/af_watch
uv venv && uv pip install -e ".[dev]"

af-watch init                  # writes ~/.af-watch/config.toml template
$EDITOR ~/.af-watch/config.toml   # github_token + home_repo + target_repos
af-watch run --window 7d
af-watch open                  # opens latest briefing.md
```

Requires the `claude` CLI on PATH. Requires a GitHub PAT with `public_repo` scope only.

## How it fits

```
af-watch  ──→  ranked opportunities  ──→  af-fix / manual  ──→  upstream draft PR
```

af-watch is the **discovery** layer: it surfaces _what to invest in this week_. Selected items are then handed off to af-fix (single-issue automated PR) or executed manually.

## Tech

Python 3.12 · `agent-framework-core` · `claude` CLI (subprocess) · `PyGithub` · `httpx` · `pydantic` v2 · `asyncio.gather` · `pytest` · `ruff` / `mypy --strict`

## Status

Phase 1 shipped: 63 unit tests passing, end-to-end pipeline runnable. Corpus seeded with 10 domain maps + 15 comparison-matrix entries + May 2026 intel; designed for human-driven monthly refresh.

Phase 2 (signposted, not built): adaptive ranking from operator decisions log, LLM-drafted corpus diffs, conformance-fuzzer reasoning channel, multi-operator sharing.
