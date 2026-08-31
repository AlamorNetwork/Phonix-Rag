from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    # The provider's own billed cost for this request, when it reports one. Preferred over
    # our price-table estimate (spec section 27: use real usage from the provider if available).
    provider_cost: float | None = None
    raw: dict[str, Any] | None = None


class ModelProvider(ABC):
    """Every model call in the system goes through this interface - no agent or orchestrator
    code talks to a provider's HTTP API directly. Swapping/adding providers (OpenAI, Anthropic,
    a custom gateway) means implementing this, nothing else.
    """

    name: str

    @abstractmethod
    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult: ...

    @abstractmethod
    def estimate_cost(
        self,
        *,
        input_price_per_1m: float,
        output_price_per_1m: float,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
    ) -> float: ...


class ProviderError(RuntimeError):
    """A provider refused or failed a request. Carries the provider's own explanation, so a
    failure is diagnosable from the run record without reproducing it by hand."""
