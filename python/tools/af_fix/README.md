# af-fix

Local CLI: triage open-source issues across configured repos, drive OpenHands in Docker to fix them, open cross-fork draft PRs.

Triage layer built on `agent-framework`. Fix layer driven by `openhands-sdk` (Claude Opus 4.7).

## Install

```bash
cd python/tools/af_fix
uv sync
```

Requires Docker running locally.

## Configure

`~/.af-fix/config.toml`:

```toml
github_token = "ghp_xxx"            # PAT, public_repo scope only
fork_owner   = "your-github-login"
anthropic_api_key = "sk-ant-xxx"

target_repos = [
    "microsoft/agent-framework",
    "vllm-project/vllm",
    # ... must have your fork of each
]
```

You must have pre-forked each repo in `target_repos` to your account.

## Run

```bash
# Score only
uv run af-fix --top 5 --triage-only

# Full run
uv run af-fix --top 5

# Local dry: no push, no PR
uv run af-fix --top 1 --no-push

# Override repo list
uv run af-fix --repos microsoft/agent-framework --top 3

# Retry failed
uv run af-fix --retry-failed --top 5

# Force retry one issue
uv run af-fix --retry-id microsoft/agent-framework:5887
```

## Two-step workflow (recommended)

Instead of running fix + PR in one shot, you can:

```bash
# Step 1: triage only, get a todolist file
af-fix triage --top 20
# (writes ~/.af-fix/todolist-2026-05-18T103000Z.md and .json)

# Step 2: open the .md file, check [x] the items you want to attempt, save.

# Step 3: execute the checked items
af-fix execute --from ~/.af-fix/todolist-2026-05-18T103000Z.md
# (will ask y/N/edit per successful fix before opening the PR)

# Skip per-PR confirmation if you trust the agent's output:
af-fix execute --from ~/.af-fix/todolist-...md --auto-submit
```

For per-PR confirm: `y` opens the PR, `N` records as rejected (won't be re-tried by default), `edit` keeps the workspace + branch for you to take over manually.

For the legacy one-shot mode, use `af-fix run --top 5`.

## Safety status (Phase 1)

WARNING: **Phase 1 limitation:** OpenHands currently runs in-process (LocalConversation), not in Docker.
The agent has the same filesystem and network access as the calling process. Run only against
trusted repos until the Docker-backed RemoteConversation path is wired (see TODO in
src/af_fix/openhands_runner.py).

- All PRs opened as **draft**. Tool never marks ready-for-review.
- Branch must be prefixed `af-fix/issue-`; submitter rejects others.
- Fork owner verified against GitHub authenticated user at startup.
- Set `AF_FIX_DISABLED=1` to disable. CI environments must set this.

## Design

See [the spec](../../../docs/superpowers/specs/2026-05-16-af-fix-agent-design.md).
