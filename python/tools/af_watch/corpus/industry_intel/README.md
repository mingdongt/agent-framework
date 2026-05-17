# Industry intel corpus

Monthly rolling markdown files. Each entry: a date stamp, 2-5 lines,
source URL.

Filename: `YYYY-MM.md`.

Phase 1 workflow:
1. `af-watch run` invokes the industry crawler, raw items dump to
   `~/.af-watch/feeds/industry_crawl/<window>.jsonl`
2. `af-watch corpus refresh` walks operator through promoting vetted
   raw items into the current month's intel file.
