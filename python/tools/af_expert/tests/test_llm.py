from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from af_expert.llm import LLM, LLMResponse, parse_json_block


def test_parse_json_block_extracts_fenced() -> None:
    content = "Here is the answer:\n\n```json\n{\"score\": 5}\n```\n\nThanks."
    assert parse_json_block(content) == {"score": 5}


def test_parse_json_block_extracts_bare() -> None:
    content = '{"score": 5}'
    assert parse_json_block(content) == {"score": 5}


def test_parse_json_block_raises_on_no_json() -> None:
    with pytest.raises(ValueError):
        parse_json_block("no json here")


def test_llm_complete_invokes_anthropic_with_caching() -> None:
    fake_client = MagicMock()
    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="hello world")]
    fake_msg.usage.input_tokens = 100
    fake_msg.usage.output_tokens = 20
    fake_msg.usage.cache_read_input_tokens = 0
    fake_msg.usage.cache_creation_input_tokens = 0
    fake_client.messages.create.return_value = fake_msg

    llm = LLM(api_key="sk-ant-test", _client=fake_client)
    resp = llm.complete(
        system="long system prompt with big context",
        user="short user prompt",
    )

    assert isinstance(resp, LLMResponse)
    assert resp.text == "hello world"
    assert resp.input_tokens == 100

    call = fake_client.messages.create.call_args
    # System message has cache_control on large context blocks
    system_arg = call.kwargs["system"]
    assert isinstance(system_arg, list)
    assert any(
        block.get("cache_control", {}).get("type") == "ephemeral" for block in system_arg
    )
