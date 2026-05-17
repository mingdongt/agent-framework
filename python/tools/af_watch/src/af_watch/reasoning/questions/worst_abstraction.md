# worst_abstraction

## Question
Which abstraction in the home framework is worst, by comparison to how competing frameworks handle the same concern? Specifically: are there cases where another framework's abstraction is cleaner AND has stability track record (≥3 months without major change)?

## Inputs
- `corpus/domain_map/<all-repos>.md`
- `corpus/comparison_matrix/features.yaml`
- `feeds/activity/<window>.jsonl` — abstraction refactor PRs in others

## System prompt
You are a senior engineer evaluating design borrowing opportunities.
For each abstraction concern (tool registry, message threading, streaming
state, memory, etc.):

1. Compare home framework's approach to ≥ 2 others.
2. Score on clarity + stability + extensibility.
3. If a competitor's abstraction is meaningfully better AND has been stable
   ≥ 3 months → emit `design-borrow` opportunity.

The action is NOT to port immediately. It's to write a comparative analysis
doc that names what's worth borrowing.

Respond with JSON only.

## Output schema
Same as feature_lag.md, opportunity type = `design-borrow`. Effort: 1w+.
Risk: high (touches public API). Risk rationale must address API stability.
