from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProviderSource:
    name: str
    url: str
    kind: Literal["html", "json", "rss"]
    description: str = ""


PROVIDER_SOURCES: list[ProviderSource] = [
    ProviderSource(
        name="anthropic",
        url="https://docs.anthropic.com/en/release-notes/api",
        kind="html",
        description="Anthropic API release notes",
    ),
    ProviderSource(
        name="openai",
        url="https://platform.openai.com/docs/changelog",
        kind="html",
        description="OpenAI API changelog",
    ),
    ProviderSource(
        name="google",
        url="https://ai.google.dev/gemini-api/docs/changelog",
        kind="html",
        description="Google Gemini API changelog",
    ),
]
