# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
import respx

from af_watch.feeds.industry_crawler import IndustryCrawler


class _StubLLM:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls = 0

    async def complete_json(self, *, system: str, user: str, max_retries: int = 2) -> Any:
        out = self.payloads[self.calls]
        self.calls += 1
        return out


@pytest.mark.asyncio
@respx.mock
async def test_crawls_whitelist_only() -> None:
    respx.get("https://anthropic.com/news").mock(
        return_value=httpx.Response(200, text="<html><body>News content</body></html>")
    )
    llm = _StubLLM([
        {
            "entries": [
                {
                    "timestamp": "2026-05-15T00:00:00Z",
                    "title": "MCP 2025-06 draft",
                    "summary": "OAuth resource tightening",
                    "url": "https://anthropic.com/news/mcp",
                }
            ]
        }
    ])
    crawler = IndustryCrawler(llm=llm, sources=["https://anthropic.com/news"])
    entries = await crawler.crawl(since=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert len(entries) == 1
    assert entries[0].title == "MCP 2025-06 draft"


@pytest.mark.asyncio
@respx.mock
async def test_skips_unreachable_source() -> None:
    respx.get("https://example.com/down").mock(return_value=httpx.Response(503))
    respx.get("https://example.com/up").mock(return_value=httpx.Response(200, text="ok"))
    llm = _StubLLM([{"entries": []}])
    crawler = IndustryCrawler(
        llm=llm,
        sources=["https://example.com/down", "https://example.com/up"],
    )
    await crawler.crawl(since=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert llm.calls == 1


@pytest.mark.asyncio
@respx.mock
async def test_filters_entries_older_than_since() -> None:
    respx.get("https://anthropic.com/news").mock(
        return_value=httpx.Response(200, text="news")
    )
    llm = _StubLLM([
        {
            "entries": [
                {
                    "timestamp": "2026-05-15T00:00:00Z",
                    "title": "recent",
                    "summary": "x",
                    "url": "https://anthropic.com/r",
                },
                {
                    "timestamp": "2026-04-01T00:00:00Z",
                    "title": "old",
                    "summary": "x",
                    "url": "https://anthropic.com/o",
                },
            ]
        }
    ])
    crawler = IndustryCrawler(llm=llm, sources=["https://anthropic.com/news"])
    entries = await crawler.crawl(since=datetime(2026, 5, 10, tzinfo=timezone.utc))
    assert len(entries) == 1
    assert entries[0].title == "recent"
