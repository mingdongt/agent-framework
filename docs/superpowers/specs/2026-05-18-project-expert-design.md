# project-expert: Claude Code plugin for becoming an expert on tracked OSS projects

**Date:** 2026-05-18
**Status:** Design approved, ready for implementation plan
**Scope:** Phase 1 — single-user local plugin; mirror + KG + MCP server + subagent + slash skills

## Goal

A Claude Code plugin that turns Claude into a domain expert on a configurable set of open-source projects. The plugin provides:

1. **Local source-of-truth mirrors** (daily git pull) so answers about APIs, internals, and idioms are grounded in current code rather than training data.
2. **LLM-generated knowledge graphs** (weekly refresh via `understand-anything`) so architecture, layering, and entity-relationship questions can be answered structurally.
3. **A stdio MCP server** exposing `projects.*` tools (search, read, symbol, changelog, kg, compare, examples, issues, refresh).
4. **A `project-expert` subagent** that must consult the MCP tools and cite `file:line` references before answering project questions.
5. **Slash-command skills** for adding/removing/refreshing tracked projects and explicitly invoking the subagent.

The plugin is **project-agnostic** — initially seeded with agent frameworks but designed to track any GitHub project (transformers, vllm, kubernetes, anything).

## Non-goals

- ❌ Not a CI bot — refresh is triggered by external schedulers or user commands.
- ❌ Not multi-user / cross-machine — each user maintains their own `~/.config/project-expert/`.
- ❌ Not a replacement for official docs — when projects have authoritative docs, the subagent cites them alongside source.
- ❌ Not a vector / embedding search engine in Phase 1 — ripgrep + symbol index suffices until proven insufficient.
- ❌ Not a web UI — Claude Code's terminal/native UI is the interface.
- ❌ Not a versioned KG store — only the latest KG per project is retained.
- ❌ Not a writer — does not respond to issues, does not open PRs, does not push.

## Architecture

### Plugin file layout

```
~/.claude/plugins/project-expert/
├── plugin.json                          # manifest: declares mcp_servers, agents, skills
├── README.md
├── pyproject.toml                       # uv-installable; deps: mcp, pygithub, pydantic, tomli
├── mcp/
│   └── server.py                        # stdio MCP server entrypoint
├── agents/
│   └── project-expert.md                # subagent definition
├── skills/
│   ├── add/SKILL.md
│   ├── remove/SKILL.md
│   ├── list/SKILL.md
│   ├── refresh/SKILL.md
│   ├── enrich/SKILL.md
│   └── ask/SKILL.md
├── scripts/
│   ├── sync.py                          # daily-pull entrypoint (cron / Task Scheduler calls this)
│   ├── kg_refresh.py                    # weekly KG refresh entrypoint
│   └── add_project.py
├── src/project_expert/
│   ├── __init__.py
│   ├── config.py                        # ~/.config/project-expert/config.toml loader
│   ├── state.py                         # ~/.config/project-expert/state.json
│   ├── mirror.py                        # git clone / pull manager
│   ├── kg_runner.py                     # invokes understand-anything; consumes its output
│   ├── kg_store.py                      # reads graph.json / nodes.json
│   ├── search.py                        # ripgrep wrapper, symbol index lookup
│   ├── github_issues.py                 # live GitHub API for `projects.issues`
│   ├── models.py                        # pydantic: Project, Snippet, Symbol, ChangelogEntry, KGNode...
│   └── tools/                           # implementation behind each MCP tool
│       ├── list.py
│       ├── search.py
│       ├── read.py
│       ├── symbol.py
│       ├── changelog.py
│       ├── kg.py
│       ├── compare.py
│       ├── examples.py
│       ├── issues.py
│       └── refresh.py
└── tests/
    ├── test_config.py
    ├── test_state.py
    ├── test_mirror.py
    ├── test_search.py
    ├── test_tools_*.py                  # one per MCP tool
    ├── test_mcp_server.py
    └── e2e/test_smoke.py
```

### User data layout

Plugin code and user data are kept strictly separate so that uninstalling the plugin never loses data.

```
~/.config/project-expert/
├── config.toml                          # user-edited
├── state.json                           # plugin-managed
└── data/
    ├── mirrors/<owner>__<repo>/         # git clone (depth=200)
    ├── kg/<owner>__<repo>/               # understand-anything output (graph.json, nodes.json, ...)
    └── index/<owner>__<repo>/            # symbol index (JSON), built during sync
```

### Component map

```
                    ┌─────────────────────────────────────┐
                    │ Claude Code (main agent)            │
                    └────────────┬────────────────────────┘
                                 │ delegates project questions to
                                 ▼
                    ┌─────────────────────────────────────┐
                    │ project-expert subagent             │
                    │ (calls projects.* tools, cites src) │
                    └────────────┬────────────────────────┘
                                 │ MCP stdio
                                 ▼
                    ┌─────────────────────────────────────┐
                    │ MCP server (mcp/server.py)          │
                    │  projects.list / search / read /    │
                    │  symbol / changelog / kg / compare /│
                    │  examples / issues / refresh        │
                    └───┬──────────────┬──────────────┬───┘
                        │              │              │
                        ▼              ▼              ▼
                ┌──────────────┐ ┌──────────┐ ┌─────────────┐
                │ mirrors/     │ │ kg/      │ │ GitHub API  │
                │ (git clones) │ │ (JSON)   │ │ (issues)    │
                └──────────────┘ └──────────┘ └─────────────┘
                       ▲              ▲
                       │              │
                ┌──────┴───────┐ ┌────┴────────────────────┐
                │ scripts/     │ │ understand-anything     │
                │ sync.py      │ │ (invoked by             │
                │ kg_refresh.py│ │  scripts/kg_refresh.py) │
                └──────────────┘ └─────────────────────────┘
                       ▲
                       │ external cron / Task Scheduler
                       │ (daily, weekly)
                  ┌────┴────┐
                  │ User OS │
                  └─────────┘
```

### Key architectural choices

- **Plugin format for first-class Claude Code integration.** MCP server, subagent, and skills all auto-register via `plugin.json`. No manual config in `~/.claude/.mcp.json` or `~/.claude/agents/`.
- **Code and data fully decoupled.** Plugin can be reinstalled / upgraded without touching `~/.config/project-expert/`. Data survives plugin removal.
- **stdio MCP, not HTTP.** Single-user, single-machine; stdio is simplest and matches Claude Code's default MCP transport.
- **External scheduling.** Plugin does not run cron internally. Provides commands; user wires them into OS scheduler (cron / launchd / Task Scheduler). README provides three-platform examples.
- **Lazy fallback refresh.** When MCP tools detect stale mirror or KG, they can opportunistically trigger refresh — so the tool is usable even if the user never sets up scheduling.
- **Project ID = `owner/repo`.** Stable, GitHub-aligned. Nicknames are search-only aliases.
- **No embedding index in Phase 1.** Ripgrep + symbol index covers most queries. Embeddings (sqlite-vec or similar) deferred until proven necessary.
- **GitHub issues queried live.** Mirrors don't store issue data; mirror-based issue search would always be stale. Issues hit GitHub Search API on demand.

## Configuration

### `~/.config/project-expert/config.toml`

```toml
[settings]
mirrors_dir = "~/.config/project-expert/data/mirrors"
kg_dir = "~/.config/project-expert/data/kg"
index_dir = "~/.config/project-expert/data/index"
clone_depth = 200
default_branch_fallback = "main"

[llm]
provider = "anthropic"                                  # anthropic | openai | azure_openai
model = "claude-opus-4-7"
api_key_env = "ANTHROPIC_API_KEY"
# Alternative: api_key_file = "~/.config/project-expert/api_key"

[refresh]
mirrors_max_age_hours = 24
kg_max_age_days = 7
kg_force_on_drift_commits = 50

[[projects]]
repo = "microsoft/agent-framework"
nickname = "agent-framework"
languages = ["python", "csharp"]
tier = "deep"

[[projects]]
repo = "langchain-ai/langgraph"
nickname = "langgraph"
languages = ["python", "javascript"]
tier = "deep"
```

**Tier semantics:**

- `deep` — mirror + KG + symbol index. Subagent can use all `projects.*` tools.
- `mirror_only` — mirror + symbol index, no KG. Tools that need KG return "no KG for this project, run `/project-expert:enrich`".
- `docs_only` — sparse clone of `docs/`, `README.md`, `samples/`, `examples/` only. Saves disk for huge repos.

**Constraints:**

- `provider` ∈ {`anthropic`, `openai`, `azure_openai`}; controls both KG generation and subagent LLM. (Subagent itself is invoked by Claude Code's model setting; this `[llm]` block governs the *background* LLM calls done by `kg_refresh.py`.)
- API key must come from env var or file; never inline in TOML.
- `repo` field is required per project; `nickname` is optional but searchable.

### `~/.config/project-expert/state.json` (plugin-managed)

```json
{
  "version": 1,
  "projects": {
    "microsoft/agent-framework": {
      "last_pulled_at": "2026-05-18T03:00:00Z",
      "last_pulled_sha": "286bfcb9e...",
      "last_kg_refreshed_at": "2026-05-13T03:00:00Z",
      "last_kg_source_sha": "d46e57072...",
      "kg_status": "ok",
      "last_error": null,
      "commits_since_kg": 47
    }
  }
}
```

`kg_status` ∈ {`ok`, `stale`, `failed`, `running`, `missing`}.

## MCP server tools

All tools live under the `projects` namespace.

| Tool | Args | Returns | Notes |
|---|---|---|---|
| `projects.list` | `tier?: str` | `[{repo, nickname, tier, last_pulled_at, last_kg_refreshed_at, kg_status, commits_since_kg}]` | Enumerate tracked projects. |
| `projects.search` | `project: str, query: str, kind: "code"\|"docs"\|"samples"="code", glob?: str, max_results: int=20` | `[{path, line, snippet, score}]` | Ripgrep with file-type filter. `score` boosts symbol-matching paths. |
| `projects.read` | `project: str, path: str, ref: str="HEAD", line_range?: [int, int]` | `{content, lines, sha}` | Read a file at a specific commit/tag/HEAD. Optional line range. |
| `projects.symbol` | `project: str, name: str, kind: "class"\|"function"\|"any"="any"` | `[{path, line, kind, signature, docstring}]` | Cross-file symbol resolution via pre-built index. |
| `projects.changelog` | `project: str, since: str, limit: int=50` | `[{sha, author, date, subject, files_changed}]` | `since` accepts ISO date or SHA. |
| `projects.kg` | `project: str, layer?: str, node_id?: str` | `{nodes, edges, layers}` or `{node, neighbors}` | Returns full KG, single layer, or a node's local neighborhood. |
| `projects.compare` | `concept: str, projects: [str]` | `[{project, snippets, idiomatic_example}]` | Cross-project concept lookup. Performs symbol + grep per project. |
| `projects.examples` | `project: str, concept: str` | `[{path, snippet}]` | Restricted to `samples/`, `examples/`, `getting_started/`, `tutorials/`, `cookbook/`. |
| `projects.issues` | `project: str, query: str, state: "open"\|"closed"\|"all"="open", limit: int=20` | `[{number, title, url, labels, comments, created_at}]` | Live GitHub Search API. |
| `projects.refresh` | `project?: str, force_kg: bool=false` | `{project, mirror_status, kg_status, error?}` | Synchronous refresh. Use sparingly; prefer scheduled refresh. |

**Error contract:** every tool may return `{"error": "<code>", "message": "<human>"}` with codes:

- `project_not_tracked` — project missing from config
- `mirror_missing` — config has the project but no clone yet
- `kg_missing` — `tier=deep` but no KG (suggest `/project-expert:enrich`)
- `mirror_stale` — last_pulled > 7d (non-blocking warning)
- `not_found` — path/symbol/node not present
- `upstream_unavailable` — GitHub API down or rate-limited

## Subagent definition

`agents/project-expert.md` (full content):

```markdown
---
name: project-expert
description: Use for any in-depth question about a tracked open-source project's
  architecture, APIs, internals, idioms, version differences, or how to express
  a concept in that project's style. MUST consult projects.* MCP tools and cite
  file:line references before answering. Do NOT rely on training-data knowledge
  for current API surfaces.
tools:
  - projects.list
  - projects.search
  - projects.read
  - projects.symbol
  - projects.changelog
  - projects.kg
  - projects.compare
  - projects.examples
  - projects.issues
  - WebSearch
  - WebFetch
  - Read
  - Grep
  - Glob
---

You are an expert on the user's tracked open-source projects.

# Workflow

1. Identify the project(s) the question concerns. If unclear, call projects.list
   and infer from context. If still ambiguous, ask once.

2. For "what does X look like" / API questions:
   - projects.symbol to locate the entity
   - projects.read to fetch the source
   - Cite file:line in the answer

3. For "how is X implemented internally" mechanism questions:
   - projects.kg for architectural context
   - projects.search for call sites / related modules
   - projects.read for the actual implementation
   - Cite file:line for each load-bearing claim

4. For "what changed" questions:
   - projects.changelog with since=<date or version>
   - Optionally projects.issues for related discussion

5. For "how does X compare across projects":
   - projects.compare or parallel projects.symbol calls
   - Present a clear comparison table

6. For "is this still current" sanity checks:
   - Check projects.list for last_pulled_at
   - If stale, mention it and suggest /project-expert:refresh

# Rules

- NEVER assert current API behavior without a corresponding projects.read or
  projects.symbol citation.
- If the answer requires data the tools cannot provide (unreleased features,
  community discussion), WebSearch first; if nothing useful, say so explicitly.
- Output structure: lead with the answer, then evidence (cited snippets), then
  nuances/caveats.
- Length: match the question. Don't pad with subsections.
```

## Skills (slash commands)

| Skill | Trigger | Behavior |
|---|---|---|
| `/project-expert:add <repo>` | Track a new project | Append to config, clone immediately, optionally schedule KG enrichment. Accepts `owner/repo` or full GitHub URL. |
| `/project-expert:remove <project>` | Stop tracking | Confirm, remove from config, delete data dir. |
| `/project-expert:list` | Show tracked state | Table of projects with last_pulled, kg_status, drift. |
| `/project-expert:refresh [--project X] [--force-kg]` | Manual refresh | Calls `scripts/sync.py` (and `kg_refresh.py` if `--force-kg`). |
| `/project-expert:enrich <project>` | Force KG regen | Subset of refresh; KG-only. |
| `/project-expert:ask <question>` | Explicit expert query | Dispatches the `project-expert` subagent with the question. |

`SKILL.md` files follow the standard plugin skill format. `ask` is the only skill that delegates to the subagent; others operate on plugin state directly.

## Sync logic

### Daily sync (`scripts/sync.py`)

```
for project in config.projects:
    if project.tier == "docs_only":
        sparse_pull(project)
    else:
        full_pull(project, depth=settings.clone_depth)
    rebuild_symbol_index(project)
    state.record_pull(project, sha=current_head)
```

**Symbol index generation:** `rebuild_symbol_index` walks the mirror, parses each source file with a light AST/tree-sitter pass, and writes a single JSON to `data/index/<project>/symbols.json` mapping `{name → [{path, line, kind, signature}]}`. No LLM involved. Phase 1 supports Python (via Python's `ast` module); other languages fall back to a regex-based scanner extracting top-level `def`/`class`/`function`/`fn`/etc. patterns. Tree-sitter integration is a Phase 2 polish.

### Weekly KG refresh (`scripts/kg_refresh.py`)

```
for project in config.projects where tier == "deep":
    drift = git_commits_since(state.last_kg_source_sha, "HEAD")
    if drift == 0:
        continue                                    # nothing changed
    if drift < settings.refresh.kg_force_on_drift_commits and not weekly_tick:
        continue                                    # too few commits; wait
    invoke understand-anything (LLM-driven) on project mirror
    write KG output to data/kg/<project>/
    state.record_kg_refresh(project, sha=current_head)
```

### Lazy fallback

When any `projects.*` MCP tool detects that `last_pulled_at` exceeds `mirrors_max_age_hours`, it can (a) return results with a `stale_warning` field, and (b) optionally trigger an async pull via `projects.refresh(project=X)` — the next call will get fresh data.

### KG cost control

LLM-driven KG regen is expensive. The drift check above (`kg_force_on_drift_commits`) prevents unnecessary regen. Additionally, the `[llm]` block lets the user point KG generation at a cheaper model (e.g., `claude-sonnet-4-6`) even when the subagent itself runs on Opus.

## Usage discipline (Tier 4)

Three guardrails to ensure the tools are actually used:

1. **Subagent description.** Strong activation phrase ("Use for any in-depth question...") so main-agent automatically delegates project questions.
2. **Subagent rules.** Hard rule: no API claim without a `projects.read` or `projects.symbol` citation. Modeled as a non-negotiable constraint inside the subagent prompt.
3. **User-level memory entry.** A line in the user's Claude Code auto-memory (`~/.claude/projects/<project>/memory/MEMORY.md` or the global equivalent) instructing main-agent to delegate to `project-expert` for tracked projects. Created by `/project-expert:add` on first installation, idempotent on subsequent calls.

## Error handling

| Scenario | Behavior |
|---|---|
| `add` for a repo that doesn't exist on GitHub | Detect via API ping, refuse, surface clear message. |
| Clone fails (auth, network) | Mark `kg_status: failed`, record `last_error`, continue with other projects. |
| KG generation crashes mid-run | `kg_status: failed`, preserve previous KG, log error. Retry next schedule tick. |
| GitHub API rate limit on `projects.issues` | Return `{"error": "upstream_unavailable", "retry_after": <seconds>}`. |
| MCP tool called on `project_not_tracked` | Return clear error suggesting `/project-expert:add`. |
| User edits config with malformed TOML | `add`/`refresh` fail with line-numbered parse error; old config preserved. |
| `~/.config/project-expert/` missing | First MCP call bootstraps it with an empty config. |
| Plugin upgrade with schema migration | `state.json` `version` bumps; migration runs on load; users see migration log. |
| Cron not configured | Plugin still works via lazy fallback. README highlights this is degraded mode. |

## Security & boundaries

| Risk | Mitigation |
|---|---|
| LLM API key leakage via logs | API key only loaded from env or external file; never logged. |
| Malicious project repo (post-checkout hook, etc.) | `git clone --no-checkout` not used; checkout runs on user's machine. **Tracked repos are implicitly trusted by the user.** Documented in README. |
| `projects.read` exposing files outside the mirror | Tool resolves paths to absolute and verifies they live under the mirror directory; rejects otherwise. |
| `projects.refresh` triggering expensive LLM calls unexpectedly | `force_kg=true` requires explicit user opt-in (via skill or MCP arg). Lazy fallback only does git pull, not KG. |
| MCP server consuming runaway memory on huge KGs | KG JSON streamed when possible; `projects.kg` defaults to summary mode; full graph requires explicit `node_id=<root>`. |

## Testing strategy

### Layer 1 — Unit tests (offline, no LLM, no network)

- `config.py` — TOML load, schema validation, error messages.
- `state.py` — load/save, migration, concurrent-write guard.
- `mirror.py` — clone/pull with a local bare-repo fixture; sparse pull semantics for `docs_only`.
- `search.py` — ripgrep wrapper, glob filter, scoring.
- `kg_store.py` — load understand-anything output JSON, layer/node queries.
- `tools/*.py` — each MCP tool handler with mocked dependencies.

### Layer 2 — Integration (mock LLM, real subprocesses)

- `sync.py` end-to-end against local bare repos.
- `kg_refresh.py` with a stub `understand-anything` invocation that writes a canned `graph.json`.
- MCP server boot + protocol smoke (start server, list tools, call each tool, validate schemas).

### Layer 3 — End-to-end (real LLM, real GitHub, manual)

- `/project-expert:add microsoft/agent-framework`
- `/project-expert:refresh --force-kg --project microsoft/agent-framework`
- `/project-expert:ask "How does AgentSession persist messages?"` — assert response contains `file:line` citations.
- Marked `@pytest.mark.e2e`; never in CI.

Layers 1 and 2 run in CI; Layer 3 is operator-driven.

## Out of scope for Phase 1

- ❌ Embedding / vector search (sqlite-vec, chroma, etc.)
- ❌ Cross-user / cross-machine sharing
- ❌ Web UI / dashboard for tracked projects
- ❌ Historical KG snapshots (only the latest KG is retained)
- ❌ Automated issue/PR creation
- ❌ Watching upstream (push notifications on new releases)
- ❌ Per-project LLM provider overrides (one global `[llm]` block only)

## Phase 2 signposting

- **Embedding index** alongside ripgrep for semantic search.
- **Cross-project memory** — let the subagent record findings ("LangGraph 0.3 deprecated X") to a notes store, queried in future answers.
- **Release watcher** — periodic GitHub releases API poll; notify user on new versions for tracked projects.
- **Web dashboard** — reuse `understand-anything`'s dashboard pattern for browsing KGs.
- **Bring-your-own MCP backend** — e.g., point the plugin at an existing local code-index service.
