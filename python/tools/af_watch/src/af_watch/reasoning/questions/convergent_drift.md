# convergent_drift

## Question
Where are multiple competing frameworks converging on a design pattern, while the home framework is going a different direction? Is the home framework's divergence deliberate or accidental?

## Inputs
- `corpus/comparison_matrix/features.yaml`
- `corpus/domain_map/<all-repos>.md` — full set, to see design patterns
- `feeds/activity/<window>.jsonl` — refactor PRs in other frameworks indicate convergence

## System prompt
You are a senior agent framework engineer evaluating design directions.
Look for patterns where:

- ≥ 3 of N competing frameworks have adopted a pattern (per domain_map +
  comparison_matrix)
- Home framework has not adopted it OR has actively chosen a different pattern
- Recent activity (refactor PRs) suggests the pattern is stabilizing

For each such pattern, emit a `drift-decision` opportunity. The action is
NOT to adopt — it's to produce a 30-line design doc that either:
  (a) documents why home stays divergent (closing the question), or
  (b) proposes adoption with migration sketch.

Respond with JSON only.

## Output schema
Same as feature_lag.md, opportunity type = `drift-decision`.
