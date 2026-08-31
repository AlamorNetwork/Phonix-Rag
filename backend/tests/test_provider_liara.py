import json

import httpx
import pytest

from app.providers.liara import LiaraProvider


def _mock_transport(response_json: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json=response_json)

    return httpx.MockTransport(handler)


async def test_chat_parses_plain_text_response():
    transport = _mock_transport(
        {
            "choices": [{"message": {"role": "assistant", "content": "hello there"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }
    )
    provider = LiaraProvider(api_key="test-key", base_url="https://ai.liara.ir/api/v1", transport=transport)

    result = await provider.chat(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])

    assert result.content == "hello there"
    assert result.tool_calls == []
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 4


async def test_chat_parses_tool_calls():
    transport = _mock_transport(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "filesystem.read",
                                    "arguments": json.dumps({"path": "README.md"}),
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 8},
        }
    )
    provider = LiaraProvider(api_key="test-key", base_url="https://ai.liara.ir/api/v1", transport=transport)

    result = await provider.chat(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": "read the readme"}],
        tools=[{"type": "function", "function": {"name": "filesystem.read", "parameters": {}}}],
    )

    assert result.content is None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "filesystem.read"
    assert result.tool_calls[0].arguments == {"path": "README.md"}


async def test_chat_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key"})

    provider = LiaraProvider(
        api_key="bad-key", base_url="https://ai.liara.ir/api/v1", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await provider.chat(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])


def test_estimate_cost():
    provider = LiaraProvider(api_key="k", base_url="https://x")
    cost = provider.estimate_cost(
        input_price_per_1k=1.0, output_price_per_1k=2.0, estimated_input_tokens=1000, estimated_output_tokens=500
    )
    assert cost == pytest.approx(1.0 + 1.0)
