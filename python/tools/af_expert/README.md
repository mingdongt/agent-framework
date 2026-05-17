# af-expert

Continuously-learning domain expert for OSS agent framework contributions.

af-expert ingests issues/PRs/releases from configured OSS repositories
daily, runs intelligence strategies to surface contribution candidates,
and produces a ranked candidate list you can review.

For end-to-end fixing+PRs of the candidates you select, pipe them to
[af-fix](../af_fix/) via `af-expert candidate export <id>`.

**Status: Wave 1 (core platform + S1 + S8).**
See [spec](../../../docs/superpowers/specs/2026-05-17-af-expert-design.md)
for the full 5-wave plan.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd python/tools/af_expert
uv sync --all-extras
```

## Setup

```bash
af-expert init
$EDITOR ~/.af-expert/config.toml
```

Required fields in `config.toml`:

- `github_token` — GitHub PAT, `public_repo` scope only
- `anthropic_api_key` — Anthropic API key (Opus 4.7 access)
- At least one `[[repos]]` entry with `owner_repo = "owner/name"`

## Run

```bash
# One ingestion + strategy run
af-expert tick

# Same, also run S8 (issue archaeology) on demand
af-expert tick --include-archaeology

# View the digest for the last day
af-expert digest --since 1d

# See ranked candidates
af-expert suggest --top 10

# Drill into one candidate
af-expert candidate show s1-abc123

# Export to a markdown spec for af-fix
af-expert candidate export s1-abc123 > /tmp/spec.md

# Mark a candidate accepted/rejected after review
af-expert candidate accept s1-abc123 --notes "ported to local fork"
af-expert candidate reject s1-abc123 --notes "false positive"

# Conversational query
af-expert ask "what's the state of MCP support across frameworks?"

# Strategy management
af-expert strategy list
af-expert strategy run s8_issue_archaeology --repo microsoft/agent-framework

# Show ingestion cursors
af-expert stats
```

## State layout

```
~/.af-expert/
├── config.toml
├── state.json          # cursors per repo
├── lock                # single-process lock
├── events.db           # SQLite + FTS5 of all ingested events
├── candidates/         # per-day JSONL of candidates
├── digests/            # per-day rendered digest markdown
└── repos/<owner>__<repo>/  # per-repo briefings (Wave 2)
```

## Wave 1 limitations

- Architecture briefings: NOT YET (Wave 2). S1 currently relies on the
  LLM's training-time knowledge of each repo's structure, which means
  lower confidence than after Wave 2 builds proper briefings.
- Strategies S2-S7: NOT YET. See spec.
- No real RAG: by design — corpus fits in Opus 4.7 context.

## Verbose logging

By default `af-expert` logs at `INFO` level (per-repo ingestion summary,
S1 pattern extraction and per-target verdicts). To see more or less:

```bash
$env:AF_EXPERT_LOG_LEVEL = "DEBUG"   # PowerShell: see skip decisions, FTS queries, etc.
export AF_EXPERT_LOG_LEVEL=DEBUG      # bash/zsh equivalent
```

To silence INFO logs (only show errors):

```bash
$env:AF_EXPERT_LOG_LEVEL = "WARNING"
```

## Troubleshooting

- `StateLockError`: another `af-expert` process is running, or a previous
  run was killed without cleanup. Remove `~/.af-expert/lock` if no other
  process is active.
- GitHub rate-limit hits: tick will report per-repo failures; rerun the
  next day or shrink your tracked repo list.
- Anthropic 429s: backoff is not yet implemented (Wave 2). For now,
  reduce tracked repos or rerun later.
