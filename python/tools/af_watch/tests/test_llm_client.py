# Copyright (c) Microsoft. All rights reserved.

import json
from typing import Any

import pytest

from af_watch.exceptions import ReasoningError
from af_watch.llm_client import LLMClient


def _runner(stdouts: list[str], returncodes: list[int] | None = None):
    """Build a fake subprocess runner returning successive outputs."""
    rcs = returncodes if returncodes is not None else [0] * len(stdouts)
    calls: list[dict[str, Any]] = []

    async def fake_run(argv: list[str], *, stdin_bytes: bytes) -> tuple[int, bytes, bytes]:
        idx = len(calls)
        calls.append({"argv": argv, "stdin": stdin_bytes.decode("utf-8")})
        return rcs[idx], stdouts[idx].encode("utf-8"), b""

    fake_run.calls = calls  # type: ignore[attr-defined]
    return fake_run


def _result_payload(text: str) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": text})


@pytest.mark.asyncio
async def test_complete_returns_result_field() -> None:
    run = _runner([_result_payload("hello world")])
    client = LLMClient(claude_path="claude", model="claude-opus-4-7", runner=run)
    out = await client.complete(system="s", user="u")
    assert out == "hello world"
    argv = run.calls[0]["argv"]
    assert "--model" in argv and "claude-opus-4-7" in argv
    assert "--system-prompt" in argv and "s" in argv
    assert "-p" in argv
    assert run.calls[0]["stdin"] == "u"


@pytest.mark.asyncio
async def test_complete_raises_on_nonzero_exit() -> None:
    run = _runner([""], returncodes=[1])
    client = LLMClient(claude_path="claude", model="claude-opus-4-7", runner=run)
    with pytest.raises(ReasoningError, match="claude CLI failed"):
        await client.complete(system="s", user="u")


@pytest.mark.asyncio
async def test_complete_raises_on_is_error_true() -> None:
    payload = json.dumps({"type": "result", "is_error": True, "result": "rate limited"})
    run = _runner([payload])
    client = LLMClient(claude_path="claude", model="claude-opus-4-7", runner=run)
    with pytest.raises(ReasoningError, match="rate limited"):
        await client.complete(system="s", user="u")


@pytest.mark.asyncio
async def test_complete_json_parses_inline_json() -> None:
    run = _runner([_result_payload('{"a": 1}')])
    client = LLMClient(claude_path="claude", model="claude-opus-4-7", runner=run)
    out = await client.complete_json(system="s", user="u")
    assert out == {"a": 1}


@pytest.mark.asyncio
async def test_complete_json_extracts_fenced_block() -> None:
    inner = "Here is the result:\n```json\n{\"x\": 2}\n```\nDone."
    run = _runner([_result_payload(inner)])
    client = LLMClient(claude_path="claude", model="claude-opus-4-7", runner=run)
    out = await client.complete_json(system="s", user="u")
    assert out == {"x": 2}


@pytest.mark.asyncio
async def test_complete_json_retries_on_parse_failure() -> None:
    run = _runner([_result_payload("not json"), _result_payload('{"x": 3}')])
    client = LLMClient(claude_path="claude", model="claude-opus-4-7", runner=run)
    out = await client.complete_json(system="s", user="u")
    assert out == {"x": 3}


@pytest.mark.asyncio
async def test_complete_json_raises_after_max_retries() -> None:
    run = _runner([_result_payload("nope"), _result_payload("still nope")])
    client = LLMClient(claude_path="claude", model="claude-opus-4-7", runner=run)
    with pytest.raises(ReasoningError, match="failed to parse"):
        await client.complete_json(system="s", user="u", max_retries=2)
