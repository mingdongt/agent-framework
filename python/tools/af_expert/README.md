# af-expert

Continuously-learning domain expert for OSS agent framework contributions.

af-expert ingests issues/PRs/releases from configured OSS repositories
daily, runs intelligence strategies to surface contribution candidates,
and produces a ranked candidate list you can review.

For end-to-end fixing+PRs of the candidates you select, pipe them to
[af-fix](../af_fix/) via `af-expert candidate export <id>`.

**Status: Wave 4 (core platform + S1 + S2 + S3 + S4 + S6 + S7 + S8 + concept graph + hypothesis tracker).**
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

### Wave 2 commands

```bash
# Generate architecture briefing for one repo (shallow git clone + LLM summarize)
af-expert refresh microsoft/agent-framework

# Refresh all configured repos
af-expert refresh --all

# Run tick with extra strategies enabled
af-expert tick --include-providers       # S4: LLM provider release tracking
af-expert tick --include-health          # S6: maintainer health metrics
af-expert tick --include-providers --include-health --include-archaeology

# Run a strategy manually
af-expert strategy run s4_provider_release
af-expert strategy run s6_maintainer_health
```

### Wave 3 commands

```bash
# Seed the concept graph with built-in 30 agent/LLM domain concepts
af-expert concept seed

# List all concepts
af-expert concept list

# Show full details for one concept
af-expert concept show mcp.oauth.refresh

# Link a concept to a repo (clones repo, runs LLM linker, persists)
af-expert concept link mcp.oauth.refresh --repo microsoft/agent-framework

# Tick with structural diff (S2) or feature propagation (S7) enabled
af-expert tick --include-structural
af-expert tick --include-propagation
af-expert tick --include-structural --include-propagation --include-providers --include-health

# Run a strategy manually
af-expert strategy run s2_structural_diff
af-expert strategy run s7_feature_propagation
```

### Wave 4 commands

```bash
# Add a hypothesis to track
af-expert hypothesis add "MCP OAuth refresh-token grants in most frameworks send the resource parameter, violating RFC 8707 §2.2"

# List active hypotheses
af-expert hypothesis list

# List all hypotheses including archived
af-expert hypothesis list --archived

# Show full details for one hypothesis
af-expert hypothesis show h-abc12345

# Archive a hypothesis (no longer verifies)
af-expert hypothesis archive h-abc12345

# Tick with S3 hypothesis verification enabled (verifies one hypothesis×repo pair per run)
af-expert tick --include-hypotheses

# Run S3 strategy manually
af-expert strategy run s3_hypothesis_verify
```

## State layout

```
~/.af-expert/
├── config.toml
├── state.json
├── lock
├── events.db
├── candidates/
├── digests/
├── traces/
├── concept_graph.json    # Wave 3: hand-curated concepts + per-repo impl links
├── hypotheses.json       # Wave 4: operator-submitted hypotheses + verification results
├── repos/<owner>__<repo>/
│   └── architecture.md
└── providers/<provider>/
    └── YYYY-MM-DD.html
```

## Wave 3 status

Wave 3 adds:

- **Concept graph**: 30 hand-curated agent/LLM domain concepts with per-repo
  implementation links. Stored as a single JSON file at `~/.af-expert/concept_graph.json`.
- **S2 cross-repo structural diff**: for each concept, identifies repos whose
  implementation hasn't been updated in >180 days. Emits "this repo is lagging on
  concept X" candidates. No LLM cost (pure JSON query).
- **S7 cross-repo feature propagation**: detects new feature PRs (title `feat:`)
  in tracked repos and proposes propagation to sister repos that don't have
  equivalent capability. LLM-driven equivalence check.

### Concept graph layout

```
~/.af-expert/concept_graph.json   # single-file JSON, atomic writes
```

## Wave 4 status

Wave 4 adds:

- **Hypothesis tracker**: operator (or LLM) can submit hypotheses like
  "MCP OAuth refresh-token grants violate RFC 8707". Stored as JSON at
  `~/.af-expert/hypotheses.json` with atomic writes.
- **S3 hypothesis verification**: each `tick --include-hypotheses` run picks one
  unverified `(hypothesis × repo)` pair, fetches the repo's architecture briefing
  (if available), and asks the LLM to judge compliance. Verified pairs are cached;
  non-compliant verdicts emit candidates. Once all repos in a hypothesis are
  verified, the hypothesis can be archived.

### Hypothesis store layout

```
~/.af-expert/hypotheses.json   # single-file JSON, atomic writes
```

### Still TBD (Wave 5+)

- S5 spec conformance fuzzer

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

### Deep trace (LLM I/O)

Every LLM call is logged to a JSONL trace file at `~/.af-expert/traces/<date>.jsonl`
with: timestamp, caller label (e.g. `s1.extract_pattern[microsoft/agent-framework#5784]`),
model, system/user preview, full response, and token usage. To inspect:

```bash
# All today's LLM calls
type $env:USERPROFILE\.af-expert\traces\2026-05-18.jsonl

# Or pipe through jq for readable output
type $env:USERPROFILE\.af-expert\traces\2026-05-18.jsonl | jq '.caller, .response'
```

To disable trace writing (e.g., for tests):

```bash
$env:AF_EXPERT_TRACE_DISABLED = "1"
```

To redirect to a custom path:

```bash
$env:AF_EXPERT_TRACE_FILE = "C:\path\to\trace.jsonl"
```

## Troubleshooting

- `StateLockError`: another `af-expert` process is running, or a previous
  run was killed without cleanup. Remove `~/.af-expert/lock` if no other
  process is active.
- GitHub rate-limit hits: tick will report per-repo failures; rerun the
  next day or shrink your tracked repo list.
- Anthropic 429s: backoff is not yet implemented (Wave 2). For now,
  reduce tracked repos or rerun later.
