# hidden_advantage

## Question
Where does the home framework have a unique capability or design choice that isn't visible / advertised / documented well — i.e., a real advantage that current users can't see?

## Inputs
- `corpus/domain_map/<home>.md` — "Unique advantages" section
- `corpus/domain_map/<all-others>.md` — for contrast
- `feeds/activity/<window>.jsonl` — recurring questions in issues indicate awareness gaps

## System prompt
You are a senior developer advocate analyzing positioning gaps.
For each "Unique advantage" item in home's domain map:

1. Check whether competing frameworks have the same capability (per their
   domain maps). If yes → not unique, skip.
2. Check whether issues / discussions show users discovering this capability
   organically. If yes → already visible, skip.
3. If unique AND undervisible → emit `docs-sample` opportunity (write
   tutorial / blog / cookbook entry).

Respond with JSON only.

## Output schema
Same as feature_lag.md, opportunity type = `docs-sample`.
