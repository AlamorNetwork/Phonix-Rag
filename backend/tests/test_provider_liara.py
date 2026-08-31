import json

import httpx
import pytest

from app.providers.liara import LiaraProvider


def _mock_transport(response_json: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.url.path.endswith(("/chat/completions", "/models"))
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


def test_estimate_cost_is_per_million_tokens():
    provider = LiaraProvider(api_key="k", base_url="https://x")
    # 1M input at $3/1M + 0.5M output at $15/1M = $3.00 + $7.50
    cost = provider.estimate_cost(
        input_price_per_1m=3.0,
        output_price_per_1m=15.0,
        estimated_input_tokens=1_000_000,
        estimated_output_tokens=500_000,
    )
    assert cost == pytest.approx(10.50)


async def test_list_models_converts_prices_to_per_million():
    """The API quotes per single token; the registry must hold the per-1M figure the provider's
    own pricing page shows - gpt-4o-mini is $0.15 in / $0.60 out per 1M."""
    transport = _mock_transport(
        {
            "data": [
                {
                    "id": "openai/gpt-4o-mini",
                    "context_length": 128000,
                    "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
                }
            ]
        }
    )
    provider = LiaraProvider(api_key="test-key", base_url="https://ai.liara.ir/api/x/v1", transport=transport)

    models = await provider.list_models()

    assert models[0]["input_price_per_1m"] == pytest.approx(0.15)
    assert models[0]["output_price_per_1m"] == pytest.approx(0.60)
