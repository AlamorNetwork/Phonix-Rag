import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.liara import LiaraProvider

MESSAGES = [{"role": "user", "content": "hi"}]
OK_BODY = {
    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}


def _provider(handler) -> LiaraProvider:
    return LiaraProvider(
        api_key="test-key",
        base_url="https://ai.liara.ir/api/x/v1",
        transport=httpx.MockTransport(handler),
        retry_base_delay=0,  # no real waiting in tests
    )


async def test_a_transient_500_is_retried_and_then_succeeds():
    """A single flaky gateway 500 previously killed a task permanently and stopped the whole
    plan - exactly what happened to a reviewer task during a real build."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": "Internal Server Error"})
        return httpx.Response(200, json=OK_BODY)

    result = await _provider(handler).chat(model="m", messages=MESSAGES)

    assert result.content == "ok"
    assert calls["n"] == 2


async def test_rate_limiting_is_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": "slow down"}) if calls["n"] < 3 else httpx.Response(200, json=OK_BODY)

    result = await _provider(handler).chat(model="m", messages=MESSAGES)

    assert result.content == "ok"
    assert calls["n"] == 3


async def test_a_bad_request_is_not_retried():
    """A 400 means we sent something the gateway will refuse just as firmly next time;
    retrying only burns time and budget."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad tool name"})

    with pytest.raises(ProviderError, match="bad tool name"):
        await _provider(handler).chat(model="m", messages=MESSAGES)

    assert calls["n"] == 1, "a 4xx must fail immediately"


async def test_an_invalid_key_is_not_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(401, json={"error": "invalid api key"})

    with pytest.raises(ProviderError):
        await _provider(handler).chat(model="m", messages=MESSAGES)

    assert calls["n"] == 1


async def test_a_timeout_is_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("too slow", request=request)
        return httpx.Response(200, json=OK_BODY)

    result = await _provider(handler).chat(model="m", messages=MESSAGES)

    assert result.content == "ok"
    assert calls["n"] == 2


async def test_it_gives_up_after_max_attempts_and_says_why():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503, json={"error": "upstream unavailable"})

    provider = LiaraProvider(
        api_key="k", base_url="https://x", transport=httpx.MockTransport(handler),
        max_attempts=3, retry_base_delay=0,
    )

    with pytest.raises(ProviderError, match="upstream unavailable"):
        await provider.chat(model="m", messages=MESSAGES)

    assert calls["n"] == 3
