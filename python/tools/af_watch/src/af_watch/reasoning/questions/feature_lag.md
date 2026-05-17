# feature_lag

## Question
Where is the home framework behind on a feature that has become de-facto standard across competing frameworks?

## Inputs
- `corpus/comparison_matrix/features.yaml` — all entries
- `corpus/domain_map/<home>.md` — home framework's current state
- `feeds/activity/<window>.jsonl` — last 7 days, for time-pressure context

## System prompt
You are a senior agent framework engineer reviewing the comparison matrix.
For each feature where the home framework is `not_implemented` and at least
half of the other frameworks are `implemented` or `in_progress`:

1. Validate the gap is real (evidence dates < 30 days).
2. Classify as intentional divergence or catch-up gap:
   - intentional → emit `drift-decision` opportunity (decision: document position vs adopt)
   - catch-up → emit `feature-parity` opportunity
3. Effort: based on feature scope (read description + dependencies).
4. Risk: additive (low) vs breaking (medium/high).

Respond with JSON only. No prose before or after.

## Output schema
```json
{
  "opportunities": [
    {
      "type": "feature-parity" | "drift-decision",
      "target": "file or module in home framework",
      "action": "PR (implement X) | RFC | design doc",
      "evidence": "comparison_matrix entry name + supporting frameworks",
      "effort": "30min | 2h | 1d | 1w | longer",
      "risk": "very low | low | medium | high",
      "risk_rationale": "1 sentence",
      "rationale": "2-3 sentences explaining why this matters"
    }
  ]
}
```
