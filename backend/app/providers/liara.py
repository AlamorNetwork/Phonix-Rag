import asyncio
import json
import logging
import time
from typing import Any

import httpx

from app.core.logging import mask_secrets
from app.providers.base import ChatResult, ModelProvider, ProviderError, ToolCall, Usage

logger = logging.getLogger(__name__)

# Transient by nature: the same request may well succeed shortly afterwards. Any other 4xx
# means the gateway will refuse it just as firmly next time.
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


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
        max_attempts: int = 3,
        retry_base_delay: float = 2.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.retry_base_delay = retry_base_delay
        # Injectable transport so tests can exercise the real request/response parsing logic
        # against a fake HTTP layer instead of hitting the network.
        self._transport = transport

    async def _request_with_retry(self, method: str, url: str, *, context: str, **kwargs) -> httpx.Response:
        """Issue a request, retrying the failures that are worth retrying.

        A gateway 5xx or a rate limit is transient - during a real run one flaky 500 otherwise
        kills the task permanently and stops the whole plan. A 4xx means we sent something the
        gateway will refuse just as firmly next time, so it fails immediately rather than
        burning three attempts and the budget on it.
        """
        last_error: ProviderError | None = None
        for attempt in range(self.max_attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
                    response = await client.request(
                        method, url, headers={"Authorization": f"Bearer {self.api_key}"}, **kwargs
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = ProviderError(
                    f"{self.name} request failed {context}: {type(exc).__name__}", retryable=True
                )
            else:
                if not response.is_error:
                    return response
                # raise_for_status() alone gives "400 Bad Request" and nothing else, which says
                # nothing about *why* the gateway refused - include the body it sent back.
                last_error = ProviderError(
                    f"{self.name} returned {response.status_code} {context}: "
                    f"{mask_secrets(response.text[:600])}",
                    retryable=response.status_code in RETRYABLE_STATUS,
                )

            if not last_error.retryable or attempt == self.max_attempts - 1:
                raise last_error

            delay = self.retry_base_delay * (2**attempt)
            logger.warning(
                "%s (attempt %d/%d); retrying in %.1fs", last_error, attempt + 1, self.max_attempts, delay
            )
            await asyncio.sleep(delay)

        raise last_error  # pragma: no cover - loop always returns or raises

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
        response = await self._request_with_retry(
            "POST", f"{self.base_url}/chat/completions", context=f"model '{model}'", json=body
        )
        latency_ms = int((time.monotonic() - started) * 1000)
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

        provider_cost = usage_data.get("cost")
        return ChatResult(
            content=choice.get("content"),
            tool_calls=tool_calls,
            usage=usage,
            latency_ms=latency_ms,
            provider_cost=float(provider_cost) if provider_cost is not None else None,
            raw=data,
        )

    async def list_models(self) -> list[dict[str, Any]]:
        """Fetch the gateway's model catalogue. Prices come back per single token; they are
        converted to per-1M here so the registry stores one consistent unit."""
        response = await self._request_with_retry(
            "GET", f"{self.base_url}/models", context="listing models"
        )
        data = response.json()
        raw_models = data.get("data") or data.get("models") or []

        models = []
        for m in raw_models:
            pricing = m.get("pricing") or {}
            models.append(
                {
                    "model_id": m.get("id"),
                    "context_window": m.get("context_length") or 0,
                    "input_price_per_1m": _per_1m(pricing.get("prompt")),
                    "output_price_per_1m": _per_1m(pricing.get("completion")),
                }
            )
        return [m for m in models if m["model_id"]]

    def estimate_cost(
        self,
        *,
        input_price_per_1m: float,
        output_price_per_1m: float,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
    ) -> float:
        return (
            (estimated_input_tokens / 1_000_000) * input_price_per_1m
            + (estimated_output_tokens / 1_000_000) * output_price_per_1m
        )


def _per_1m(price: Any) -> float:
    """The API returns a price per single token; the registry stores per 1M tokens, which is
    the unit Liara's own pricing page and every other provider quotes."""
    try:
        return float(price) * 1_000_000
    except (TypeError, ValueError):
        return 0.0
