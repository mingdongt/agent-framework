# af-expert

Continuously-learning domain expert agent for OSS agent framework contributions.

See design spec: `docs/superpowers/specs/2026-05-17-af-expert-design.md`
See Wave 1 plan: `docs/superpowers/plans/2026-05-18-af-expert-wave1.md`

## Quickstart (Wave 1)

```bash
cd python/tools/af_expert
uv sync --all-extras
af-expert init
$EDITOR ~/.af-expert/config.toml
af-expert tick
af-expert digest
af-expert suggest --top 10
```
