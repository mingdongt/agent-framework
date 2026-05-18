from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from af_expert.config import _state_dir
from af_expert.providers.sources import ProviderSource


log = logging.getLogger(__name__)

USER_AGENT = "af-expert/0.1.0 (+https://github.com/microsoft/agent-framework)"
TIMEOUT_SECONDS = 30.0


def release_cache_path(provider_name: str, when: date | None = None) -> Path:
    if when is None:
        when = datetime.now(tz=timezone.utc).date()
    base = _state_dir() / "providers" / provider_name
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{when.isoformat()}.html"


def fetch_release_page(source: ProviderSource) -> str:
    log.info("polling %s at %s", source.name, source.url)
    resp = httpx.get(
        source.url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        timeout=TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def poll_provider(source: ProviderSource) -> str:
    try:
        body = fetch_release_page(source)
    except Exception as e:
        log.warning("Failed to poll %s: %s", source.name, e)
        return ""

    try:
        cache = release_cache_path(source.name)
        cache.write_text(body, encoding="utf-8")
    except Exception as e:
        log.warning("Failed to cache %s response: %s", source.name, e)

    return body
