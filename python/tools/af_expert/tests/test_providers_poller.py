from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from af_expert.providers.poller import (
    fetch_release_page,
    poll_provider,
    release_cache_path,
)
from af_expert.providers.sources import ProviderSource


def test_release_cache_path_encodes_provider_and_date(tmp_state_dir: Path) -> None:
    from datetime import date
    p = release_cache_path("anthropic", date(2026, 5, 18))
    assert p.name == "2026-05-18.html"
    assert p.parent.name == "anthropic"


def test_fetch_release_page_uses_httpx(tmp_state_dir: Path) -> None:
    src = ProviderSource(name="anthropic", url="https://docs.anthropic.com/release-notes", kind="html")

    fake_response = MagicMock()
    fake_response.text = "<html>v1.0 released today</html>"
    fake_response.raise_for_status.return_value = None

    with patch("af_expert.providers.poller.httpx.get") as fake_get:
        fake_get.return_value = fake_response

        body = fetch_release_page(src)

    fake_get.assert_called_once()
    assert "v1.0 released today" in body


def test_poll_provider_writes_cache_and_returns_body(tmp_state_dir: Path) -> None:
    src = ProviderSource(name="anthropic", url="https://docs.anthropic.com/release-notes", kind="html")

    fake_response = MagicMock()
    fake_response.text = "<html>some release notes</html>"
    fake_response.raise_for_status.return_value = None

    with patch("af_expert.providers.poller.httpx.get") as fake_get:
        fake_get.return_value = fake_response

        body = poll_provider(src)

    assert "some release notes" in body
    cache_files = list((tmp_state_dir / "providers" / "anthropic").glob("*.html"))
    assert len(cache_files) == 1
    assert cache_files[0].read_text(encoding="utf-8") == "<html>some release notes</html>"


def test_poll_provider_returns_empty_on_http_error(tmp_state_dir: Path) -> None:
    src = ProviderSource(name="anthropic", url="https://docs.anthropic.com/release-notes", kind="html")
    with patch("af_expert.providers.poller.httpx.get") as fake_get:
        fake_get.side_effect = Exception("network down")
        body = poll_provider(src)
    assert body == ""
