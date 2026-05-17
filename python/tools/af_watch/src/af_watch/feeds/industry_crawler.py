# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime
from typing import Any, Protocol

import httpx

from af_watch.models import IndustryEntry


class _LLMProto(Protocol):
    async def complete_json(self, *, system: str, user: str, max_retries: int = 2) -> Any: ...


_SYSTEM_PROMPT = (
    "You are a research analyst summarizing AI / agent-framework / LLM industry news. "
    "Given raw HTML, extract a list of distinct news items relevant to AI agent frameworks, "
    "LLM provider releases, protocol updates (MCP / AG-UI / A2A), benchmarks, or notable "
    "papers. Skip marketing fluff. Return JSON in shape: "
    '{"entries": [{"timestamp": "ISO8601", "title": "...", "summary": "1-3 lines", "url": "..."}]}'
)


class IndustryCrawler:
    def __init__(
        self,
        *,
        llm: _LLMProto,
        sources: list[str],
        timeout: float = 30.0,
    ) -> None:
        self._llm = llm
        self._sources = sources
        self._timeout = timeout

    async def crawl(self, *, since: datetime) -> list[IndustryEntry]:
        entries: list[IndustryEntry] = []
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            for url in self._sources:
                page = await self._fetch(client, url)
                if page is None:
                    continue
                raw = await self._summarize(url, page)
                for item in raw.get("entries", []):
                    try:
                        ts = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                    except (KeyError, ValueError):
                        continue
                    if ts < since:
                        continue
                    entries.append(IndustryEntry(
                        timestamp=ts,
                        source=url,
                        title=item.get("title", ""),
                        summary=item.get("summary", ""),
                        url=item.get("url", url),
                    ))
        return entries

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            response = await client.get(url)
            if response.status_code >= 400:
                return None
            return response.text
        except httpx.HTTPError:
            return None

    async def _summarize(self, url: str, html: str) -> dict[str, Any]:
        snippet = html[:50_000]
        user = f"Source URL: {url}\n\nHTML content:\n{snippet}"
        return await self._llm.complete_json(system=_SYSTEM_PROMPT, user=user)
