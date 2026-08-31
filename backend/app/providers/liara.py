import json
import time
from typing import Any

import httpx

from app.providers.base import ChatResult, ModelProvider, ToolCall, Usage


class LiaraProvider(ModelProvider):
    """Liara AI Gateway - OpenAI-compatible chat completions API. Multiple models are reachable
    through this single account/base URL, so this is the only provider Phase 0 wires up (see
    spec section 8: providers are pluggable, OpenAI/Anthropic adapters are the same shape).
    """

    name = "liara"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Injectable transport so tests can exercise the real request/response parsing logic
        # against a fake HTTP layer instead of hitting the network.
        self._transport = transport

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        body: dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        started = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
            )
        latency_ms = int((time.monotonic() - started) * 1000)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]["message"]
        tool_calls = []
        for call in choice.get("tool_calls") or []:
            try:
                arguments = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(ToolCall(id=call["id"], name=call["function"]["name"], arguments=arguments))

        usage_data = data.get("usage") or {}
        usage = Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
            cached_tokens=(usage_data.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        )

        return ChatResult(
            content=choice.get("content"),
            tool_calls=tool_calls,
            usage=usage,
            latency_ms=latency_ms,
            raw=data,
        )

    def estimate_cost(
        self,
        *,
        input_price_per_1k: float,
        output_price_per_1k: float,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
    ) -> float:
        return (
            (estimated_input_tokens / 1000) * input_price_per_1k
            + (estimated_output_tokens / 1000) * output_price_per_1k
        )
