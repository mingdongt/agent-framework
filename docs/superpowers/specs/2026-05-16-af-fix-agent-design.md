# af-fix: AI Agent for OSS Issue Contribution

**Date:** 2026-05-16 (revised 2026-05-18)
**Status:** Design v3 — approved, implemented
**Scope:** Phase 1 — local CLI, single-issue serial execution, multi-repo OSS targets

## Revision history

- **v1 (2026-05-16):** Single-repo (microsoft/agent-framework only), agent-framework-built FixAgent with handwritten fs/verify/git tools, LocalRuntime sandbox.
- **v2 (2026-05-17):** Multi-repo OSS contribution. FixAgent replaced by OpenHandsRunner driving OpenHands in Docker. Opus 4.7. Token budget unconstrained.
- **v3 (2026-05-18):** OpenHands replaced with `claude-agent-sdk` because Microsoft enterprise auth path goes through local `claude` CLI rather than direct Anthropic API. Anthropic API key dropped from config. Architecture is unchanged otherwise — TriageAgent and ClaudeAgentRunner both call claude-agent-sdk.

## Goal

Build a local CLI tool (`af-fix`) that:

1. Pulls open issues from a configured list of target OSS repositories
2. Uses an agent-framework-built **TriageAgent** to independently score each issue's "AI-fixability"
3. Lets the operator confirm the top-N candidates across all repos
4. For each chosen issue, runs **Claude Code SDK** scoped to a clean clone of the target repo, captures the produced diff, and opens a **cross-fork draft PR** from the operator's pre-existing fork to the upstream repo
5. Persists per-issue attempt state to prevent silent retries

The TriageAgent is the **dogfood layer** — it demonstrates the value of LLM-driven orchestration. The FixAgent role is delegated to **Claude Code SDK** because it is purpose-built for "issue → patch" workloads and integrates with Microsoft enterprise auth via the local `claude` CLI.

## Non-goals

- ❌ Not a CI bot — no GitHub Actions, no cron, no webhook subscription.
- ❌ Not a published framework package — internal tool under `python/tools/`.
- ❌ Not interactive after PR creation — does not respond to review comments, does not auto-mark ready-for-review, does not close PRs.
- ❌ Not parallel — one Claude Code agent at a time. Parallelization is Phase 2.
- ❌ Not a fork manager — assumes the operator has pre-forked every target repo to their GitHub account.
- ❌ Not language-locked — Claude Code is language-agnostic; this tool targets Python, JS/TS, Go, Rust as the agent allows.

## Architecture

### File layout

```
python/tools/af_fix/
├── pyproject.toml                  # standalone uv project; deps: agent-framework-core, openhands-ai, PyGithub
├── README.md
├── src/af_fix/
│   ├── __init__.py
│   ├── cli.py                      # argparse entry; orchestrates triage → confirm → fix → submit
│   ├── state.py                    # ~/.af-fix/state.json
│   ├── config.py                   # ~/.af-fix/config.toml
│   ├── github_client.py            # PyGithub thin wrapper, multi-repo aware
│   ├── worktree.py                 # local clone manager (one workspace dir per issue)
│   ├── triage_agent.py             # TriageAgent: claude-agent-sdk, JSON scoring
│   ├── claude_agent_runner.py      # Wraps claude-agent-sdk query() for fix runs
│   ├── pr_submitter.py             # push to fork + open cross-fork draft PR
│   ├── models.py                   # Pydantic models
│   └── exceptions.py
└── tests/
    ├── conftest.py
    ├── test_state.py
    ├── test_config.py
    ├── test_github_client.py
    ├── test_worktree.py
    ├── test_triage_agent.py
    ├── test_claude_agent_runner.py
    ├── test_pr_submitter.py
    ├── test_cli.py
    └── e2e/test_smoke.py
```

### Main flow

```
1.  state.load()
2.  for repo in config.target_repos:
        issues += github.list_open_issues(repo) - state.attempted_for(repo)
3.  scores = triage_agent.score_all(issues)         # one LLM call per issue, parallelizable but Phase-1 serial
4.  top = scores.sorted_by_score()[:args.top]
5.  print(top); wait for Enter
6.  for s in top:
        repo, issue = s.repo, s.issue
        workspace = workspace_manager.create(repo, issue.number)    # git clone upstream → workspace dir
        result = claude_agent_runner.run(issue, workspace, model="claude-opus-4-7", max_turns=80)
        if result.success and result.diff_nonempty:
            branch = f"af-fix/issue-{issue.number}-{slug}"
            git.checkout_branch(workspace, branch)
            git.commit_all(workspace, message=result.summary)
            pr_submitter.submit(repo, branch, workspace, result)    # push to operator's fork; open cross-fork PR
        else:
            record state with outcome (gave_up / error)
7.  state.save()
```

### Key architectural choices

- **Triage is per-issue independent LLM calls.** No batching, no shared context. Each issue gets a fresh Opus 4.7 call with a fixed scoring rubric. Reasons: (a) per-issue prompts isolate context-pollution risk; (b) token budget is unconstrained so batching saves nothing; (c) results are more comparable when each issue is judged on its own merit.
- **Claude Code SDK runs in-process per issue.** No Docker, no container startup overhead. The `claude` CLI is invoked as a subprocess by the SDK; it runs in the operator's process space. Phase 2 will add containerization.
- **TriageAgent and ClaudeAgentRunner both use Claude Opus 4.7 (`claude-opus-4-7`).** Best available model, max budget. Cost is not a constraint.
- **`max_turns=80`** (vs default). Lets the agent dig deeper before giving up.
- **Operator pre-forks each target repo.** No GitHub fork API calls. Simpler permissions, fewer surprises, operator stays in control of which repos this tool touches.
- **Cross-fork draft PRs.** Branch pushed to `operator-fork/af-fix/issue-N-slug`; PR opened from `operator:af-fix/issue-N-slug` → `upstream:main`, always `draft=True`.
- **Workspace = full local clone of upstream/main**, one dir per issue at `~/.af-fix/workspaces/<owner>__<repo>/issue-<N>/`. Not a `git worktree` (those don't fit multi-repo well). Deleted by `af-fix gc` after PR resolved.

### CLI flag summary

| Flag | Effect |
|---|---|
| `--top N` | Number of issues to fix across all repos (default 5). |
| `--triage-only` | Score and print top-N; do not run Claude Code. |
| `--no-push` | Run Claude Code fully; skip push & PR creation. |
| `--dry-run` | Print what would happen; touch no files; no API calls. |
| `--retry-failed` | Allow re-attempt of `gave_up`/`error` outcomes. |
| `--retry-id <repo>:<N>` | Force retry of one specific issue (debug). |
| `--repos <list>` | Override config; comma-separated `owner/repo`. |

### LLM provider

`claude-agent-sdk` (wraps the local `claude` CLI). No Anthropic API key required — authenticates via Microsoft enterprise auth or personal Claude Code setup. Model defaults to `claude-opus-4-7`; configurable via `model` in `~/.af-fix/config.toml`. Both TriageAgent and ClaudeAgentRunner use the same SDK and model.

## Component: TriageAgent

**Responsibility:** For every input issue, output `{score: 0-10, reason: str, suggested_files: [str]}`. **One LLM call per issue.** No batching.

**Why per-issue:**
- Token budget unconstrained → no reason to batch
- Comparable scoring (no order-effects, no fatigue across a long context)
- Trivially parallelizable in Phase 2 (independent calls)

**Tools (single tool):**
- `submit_score(score, reason, suggested_files)` — agent calls exactly once per invocation.

**Prompt strategy:** A short system prompt (the rubric) + the issue body. The agent reads the issue, calls `submit_score` once, done. No fetch loop, no decision tree.

```
You are an OSS issue triage agent.
Score whether this issue is suitable for an AI agent to fix and PR in under 30 minutes.

High (7-10): clear error, full stack trace, reproducible; single-file or small set; no design decision.
Mid (4-6): clear error but possibly multi-file; small refactor; needs verification.
Low (0-3): feature request / discussion / proposal; needs architecture; large refactor; vague description.

Call submit_score exactly once with score, reason (one line), and suggested_files (your best guess at relevant paths).

ISSUE:
Repo: {repo}
Title: {title}
Body: {body}
```

**Output handling:** CLI collects all scores into a flat list, sorts by score descending, prints top-N with `{repo}#{number}  score  reason`, waits for Enter.

**Modes:**
- `--triage-only` → print scores only
- `--dry-run` → as above, no LLM calls (uses cached scores from previous run if available)

**Edge cases:**
- LLM returns no `submit_score` call → score=0, reason="no score returned"
- Out-of-range score → clamped to 0–10
- LLM error → score=0, reason="triage error: <details>"

## Component: ClaudeAgentRunner

**Responsibility:** Given an issue and a workspace path containing a clean clone of the target repo, drive Claude Code SDK to produce a fix; return success + diff + summary.

**Construction:** A thin wrapper around `claude-agent-sdk`'s `query()` async generator. Authenticates via the local `claude` CLI (Microsoft enterprise auth or personal Claude Code setup — no Anthropic API key required).

**Key configuration:**
- **cwd:** the local clone directory (Claude Code operates against it directly).
- **model:** `claude-opus-4-7` (default; configurable via `model` in config.toml).
- **max_turns:** 80 (default; configurable via `max_turns` in config.toml).
- **permission_mode:** `acceptEdits` — allows file edits without per-edit prompts.
- No Docker, no container startup overhead.

**Initial prompt template:**

```
You are fixing an issue in an open-source repository.

Repository: {owner/repo}
Issue #{number}: {title}

Issue body:
{body}

The repository is already checked out at /workspace. The default branch is checked out.

Your task:
1. Read the issue carefully.
2. Reproduce or confirm the bug if possible.
3. Make the minimum change required to fix it.
4. Run the test suite (or the relevant subset) and confirm it passes.
5. Write a brief one-line summary at the end like:
   SUMMARY: <conventional-commits style fix message>

Hard constraints:
- Touch only files needed for the fix.
- No new dependencies, no CI changes, no formatter sweeps.
- If the issue is too broad, malformed, or undecidable: STOP and write "GAVE_UP: <reason>".
```

**Result extraction (this is the tricky part):**

OpenHands returns a `State` object after `run_controller` completes. Steps to derive our `FixResult`:

1. Check for `GAVE_UP:` marker in the last assistant message → `gave_up=True`, reason from marker.
2. Otherwise compute `git diff origin/main` in the workspace.
3. If diff is empty and no `SUMMARY:` marker → `success=False, reason="no changes produced"`.
4. If diff is non-empty → success. Extract `SUMMARY:` from last message; fallback to first line of last commit message; fallback to `f"fix issue #{issue.number}"`.
5. Capture last 200 trajectory steps as `trajectory_excerpt` for the PR body.

**Return:**

```python
class FixResult(BaseModel):
    success: bool
    repo: str               # "owner/name"
    issue_number: int
    workspace: Path
    diff: str               # full unified diff
    summary: str | None
    trajectory_excerpt: str | None
    reason: str | None
    gave_up: bool = False
```

**Verification level inside OpenHands:**

The agent is instructed to run the test suite. We do NOT separately re-run tests after OpenHands exits. Reasons:
- OpenHands' container is the verified environment; re-running outside it is brittle
- The agent already iterates on tests as part of its loop
- The git diff is the source of truth — if it's non-empty and the agent didn't `GAVE_UP`, we treat it as the agent's verified output

**Hard boundaries:**

- OpenHands has **no GitHub API access** (no PyGithub, no token). It cannot create PRs, comment on issues, or push.
- All git operations (commit, push) happen **outside** the container, after OpenHands exits.

## Component: PR Submitter

**Responsibility:** Take a successful `FixResult` and create a cross-fork draft PR from the operator's fork.

**Pre-requisite assumptions:**
- Operator has pre-forked the upstream repo to their GitHub account (e.g., `mingdongtan/agent-framework` for upstream `microsoft/agent-framework`).
- Workspace remote `origin` points at upstream; we add a `fork` remote pointing at the operator's fork.

**Flow:**

```python
def submit(repo: str, result: FixResult, fork_owner: str) -> PRResult:
    # 1. Commit
    branch = f"af-fix/issue-{result.issue_number}-{slug(result.summary)}"
    git_checkout(result.workspace, branch)
    git_commit(result.workspace, message=f"fix: {result.summary}\n\nFixes #{result.issue_number}")
    # 2. Add fork remote if absent
    git_remote_add(result.workspace, "fork", f"git@github.com:{fork_owner}/{repo.split('/')[1]}.git")
    # 3. Push to fork
    git_push(result.workspace, "fork", branch)
    # 4. Check for existing PR
    existing = github.find_open_pr(upstream=repo, head=f"{fork_owner}:{branch}")
    if existing:
        return existing
    # 5. Create cross-fork draft PR
    return github.create_draft_pr(
        upstream=repo,
        title=f"fix: {result.summary}",
        body=render_pr_body(result),
        head=f"{fork_owner}:{branch}",
        base="main",
    )
```

**PR body template:**

```markdown
Fixes #{issue.number}

## Summary
{result.summary}

## Changes
```
{diff_stat}
```

## Agent trajectory (last 30 steps)
<details>
<summary>Claude Code trajectory excerpt</summary>

```
{trajectory_excerpt}
```
</details>

---
Drafted by `af-fix` using Claude Code SDK (claude-opus-4-7). Reviewed by @{fork_owner} before ready-for-review.
```

**Safety checks:**

1. **Branch namespace:** must start with `af-fix/issue-`. Reject otherwise.
2. **Forced draft:** `draft=True` hardcoded.
3. **Duplicate-PR detection:** check upstream for existing open PR with same `head`; if found, skip and return existing.
4. **No force-push:** plain `git push` (push fails → submitter raises → state recorded as error).
5. **Fork ownership check:** verify `fork_owner` matches the operator's GitHub user (from config); refuse if mismatch.

**Things the submitter never does:**

- Close issue, comment on issue
- Assign reviewers / add labels
- @-mention anyone
- Mark PR ready-for-review

## State management

**File:** `~/.af-fix/state.json` (single-process; simple file lock).

**Schema:**

```json
{
  "version": 2,
  "attempts": {
    "microsoft/agent-framework#5887": {
      "first_attempted": "2026-05-17T10:23:00Z",
      "last_attempted": "2026-05-17T10:23:00Z",
      "attempt_count": 1,
      "outcome": "pr_opened",
      "branch": "af-fix/issue-5887-foo",
      "pr_url": "https://github.com/microsoft/agent-framework/pull/5888",
      "give_up_reason": null
    }
  }
}
```

Key is `{repo}#{issue_number}` (multi-repo). Otherwise identical to v1.

**Outcomes:** `pr_opened`, `gave_up`, `error`, `branch_pushed_no_pr`.

**Reuse rules:** unchanged from v1 (default skip; `--retry-failed` allows gave_up/error; `--retry-id` forces; pr_opened never auto-retried).

## Configuration

`~/.af-fix/config.toml`:

```toml
# Required
github_token = "ghp_xxx"           # PAT with `public_repo` scope only
fork_owner   = "mingdongtan"        # operator's GitHub username

# Target repos (operator must have a fork of each)
target_repos = [
    "microsoft/agent-framework",
    "vllm-project/vllm",
    "AstrBotDevs/AstrBot",
    "UKGovernmentBEIS/inspect_ai",
]

# Optional
model     = "claude-opus-4-7"   # used for both triage and fix (default)
max_turns = 80                  # replaces openhands_max_iterations (default)
```

## Error handling

| Stage | Error | Handling |
|---|---|---|
| Triage | GitHub API failure / rate limit | 3 retries with backoff; abort if persistent |
| Triage | LLM error on one issue | score=0, continue |
| Triage | LLM no submit_score call | score=0, reason="no score returned" |
| Claude Code | `claude` CLI not found | Hard error, surface to operator, abort run |
| Claude Code | Authentication failure | Hard error, surface, abort |
| Claude Code | SDK error during run | Mark issue `error`, continue to next |
| Claude Code | Agent gives up (GAVE_UP marker) | Mark `gave_up`, continue to next |
| Claude Code | LLM provider error mid-run | Mark issue `error`, continue |
| Claude Code | `max_turns` exhausted | Treat as completed; if diff non-empty, submit; else error |
| PR submit | Push failure | Mark `error`, workspace retained |
| PR submit | PR creation fails post-push | Mark `branch_pushed_no_pr`, retry next run |
| Global | Ctrl+C | Mark in-flight as `error: interrupted`; flush state.json |

## Security & trust boundaries

| Risk | Mitigation |
|---|---|
| Agent runs arbitrary shell | Claude Code SDK runs in-process via local `claude` CLI; same process-level boundary as calling shell. Phase 2: containerization. Claude Code's built-in permission prompts may catch egregious actions. |
| Agent installs malicious deps | No container boundary in Phase 1; run only against trusted repos |
| Agent modifies operator's main checkout | Workspace is a separate clone; container only sees mounted workspace |
| Agent pushes a non-`af-fix/*` branch | Submitter rejects with prefix check |
| Agent force-pushes | Submitter never passes `-f`; head/base hardcoded |
| Agent comments / closes upstream issues | OpenHands has no GitHub token; submitter does only `create_pull` |
| Wrong fork_owner pushed to | Submitter verifies `fork_owner` matches authenticated user |
| Overprivileged PAT | Docs: `public_repo` scope only; PAT in config.toml, not env |
| Tool added to CI | `AF_FIX_DISABLED=1` env check at startup; CI sets this |

## Testing strategy

### Layer 1 — Unit tests (no LLM, no Docker, no network)

- `state.py` — load/save/round-trip, attempt tracking, retry rules
- `config.py` — TOML parsing, required-field validation
- `pr_submitter.py` — body rendering, branch-prefix enforcement, dup detection, fork-owner verification (GitHub client mocked)
- `github_client.py` — error translation, PR query construction
- `worktree.py` — clone directory creation, slug generation, path encoding
- `triage_agent.py` — score clamping, missing-score fallback, JSON parsing (mock `_run_claude`)
- `claude_agent_runner.py` — diff extraction logic, GAVE_UP/SUMMARY parsing (mock `_run_claude` returning shim objects)

Must run offline in seconds. In CI.

### Layer 2 — Agent simulation tests (mock LLM)

- TriageAgent driven by a mock `_run_claude` returning canned JSON; verify score clamping and fallbacks
- ClaudeAgentRunner driven by a mock `_run_claude` returning constructed shim objects; verify diff extraction across success/gave_up/empty-diff cases

Tools are real (file system, real git operations); LLM/agent is faked. In CI.

### Layer 3 — End-to-end smoke (real LLM, real Docker)

`tests/e2e/test_smoke.py`, marked `@pytest.mark.e2e`, skipped by default:

- `af-fix --triage-only --top 3 --dry-run` — verify Triage scoring sane against a real repo
- `af-fix --top 1 --no-push` — end-to-end without remote side effects against a known fixable issue

Requires `~/.af-fix/config.toml` + `claude` CLI authenticated locally. Operator runs manually.

### Safety belt-and-suspenders

- `AF_FIX_DISABLED=1` startup check (CLI exits with code 2)
- Fork owner equality check (config vs. GitHub authenticated user) at CLI startup
- Workspace path always under `~/.af-fix/workspaces/`; any other path rejected

## Phase 2 (out of scope, signposted)

- Parallel OpenHands containers (workflow primitive from agent-framework, real dogfood expansion)
- PR comment responder agent (separate session)
- GitHub Action `workflow_dispatch` wrapper
- Auto-fork management
- Cross-language quality dashboards (track success rate by language / repo)
- Iterative review feedback loop (OpenHands re-engaged on review comments)
