# af-fix

Triages selected issues across configured agent framework repos, drives OpenHands to produce a fix, and opens cross-fork draft PRs.

> Part of the **microsoft/agent-framework ecosystem-engineering initiative**
> — internal tooling supporting MAF (Microsoft's next-generation unified
> agent framework) through competitive ecosystem mapping, high-leverage
> opportunity identification, and accelerated contribution execution.
>
> Sibling tools: [af-watch](../af_watch/) (weekly editorial briefing) · [af-expert](../af_expert/) (always-on intelligence pipeline)

## What it does

- **TriageAgent** (built on `agent-framework-core`): per-issue independent LLM scoring (Claude Opus 4.7) of open issues across configured target repos — rates each on fixability, scope, and value, returns top-N.
- **Operator confirmation step**: prints the scored list and waits for human selection before any side effects.
- **OpenHandsRunner**: drives OpenHands `CodeActAgent` per selected issue (`max_iterations=80`, isolated workspace per attempt). The container has no GitHub token; all git operations happen outside it.
- **PR Submitter**: pushes the produced diff to the operator's pre-existing fork on a `af-fix/issue-N-*` branch and opens a **draft** PR to upstream. Never marks ready-for-review, never closes the source issue, never @-mentions.
- **Two-step workflow** (recommended): `af-fix triage` writes a todolist `.md`; operator checks `[x]` the items to attempt; `af-fix execute --from <list>` drives only those items, with per-PR `y/N/edit` confirmation before submission.

## Quick start

```bash
cd python/tools/af_fix
uv sync

af-fix init
$EDITOR ~/.af-fix/config.toml   # github_token + fork_owner + anthropic_api_key + target_repos

# Score only (no side effects)
af-fix --top 5 --triage-only

# Full run (asks confirmation before each PR submission)
af-fix --top 5

# Local-only (no push, no PR)
af-fix --top 1 --no-push
```

Operator must pre-fork each target repo on GitHub before running.

## Two-step workflow

```bash
# Step 1: triage only, get a checkable todolist
af-fix triage --top 20
# writes ~/.af-fix/todolist-<timestamp>.md and .json

# Step 2: open the .md file, check [x] the items to attempt, save.

# Step 3: execute only the checked items
af-fix execute --from ~/.af-fix/todolist-<timestamp>.md
# per-PR prompt: y opens the PR · N records rejected · edit keeps the workspace
# for manual takeover

# Skip per-PR confirmation if you trust the agent's output
af-fix execute --from ~/.af-fix/todolist-<timestamp>.md --auto-submit
```

For the legacy one-shot mode, use `af-fix run --top 5`.

## How it fits

```
{af-watch | af-expert | manual selection}  ──→  selected issue  ──→  af-fix  ──→  cross-fork draft PR
```

af-fix is the **execution** layer: given a specific issue to attempt, it produces a fix and opens a draft PR for human review. It does not _select_ issues to work on — that decision comes from af-watch (weekly editorial), af-expert (always-on intelligence), or the operator's own judgment.

## Tech

Python 3.12 · `agent-framework-core` (TriageAgent) · `openhands-sdk` · Anthropic Claude Opus 4.7 · `PyGithub` · Docker (Phase 2) · `pytest`

## Safety boundaries (Phase 1)

- All PRs opened as **draft** — tool never marks ready-for-review.
- Branch namespace enforced: must start `af-fix/issue-`; other prefixes rejected.
- Fork-owner verification at startup against GitHub authenticated user.
- `AF_FIX_DISABLED=1` environment gate — CI environments must set this.
- OpenHands has no GitHub token inside its runtime — all git operations happen outside.

⚠️ **Phase 1 sandbox limitation**: OpenHands currently runs in-process (`LocalConversation`), not in Docker. The agent has the same filesystem and network access as the calling process. Run only against trusted target repos until the Docker-backed `RemoteConversation` path is wired in.

## Status

Phase 1 shipped: triage + execute + cross-fork PR submission working end-to-end. Phase 2 planned: Docker `RemoteConversation` for sandbox isolation, automated review-comment response loop.
