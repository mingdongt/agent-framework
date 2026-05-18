from __future__ import annotations

from af_expert.providers.sources import PROVIDER_SOURCES, ProviderSource


def test_known_providers_present() -> None:
    names = {s.name for s in PROVIDER_SOURCES}
    assert "anthropic" in names
    assert "openai" in names
    assert "google" in names


def test_sources_have_required_fields() -> None:
    for src in PROVIDER_SOURCES:
        assert isinstance(src, ProviderSource)
        assert src.name
        assert src.url.startswith("https://")
        assert src.kind in {"html", "json", "rss"}
