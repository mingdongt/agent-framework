# Domain map corpus

Each file in this directory describes one target framework as a senior
agent-framework engineer would describe it: 60-150 lines of opinionated
markdown, NOT a README copy.

Filename: `<owner>__<repo>.md`.

## Required sections

1. Architecture in 5 sentences
2. Key design choices (taste, not docs)
3. Current pain points (last 30 days, from PR / issue clustering)
4. Unique advantages
5. Deltas vs LangChain / ADK / pydantic-ai

## Refresh

Every ~4 weeks. `af-watch corpus refresh` proposes a diff based on recent
activity; operator accepts/rejects line by line.
