"""Provider-agnostic LLM client interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass
class Message:
    role: str    # "user" | "assistant"
    content: str


class LLMClient(ABC):
    """All LLM providers implement this interface.

    Orchestration logic MUST depend only on this class, never on a concrete provider.
    """

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """Return the full completion text."""
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> Iterator[str]:
        """Yield text chunks as they arrive."""
        ...


def make_client(provider: str, model: str, api_key: str | None = None) -> LLMClient:
    """Factory — returns the right client for the given provider."""
    match provider:
        case "anthropic":
            from .anthropic_client import AnthropicClient
            return AnthropicClient(model=model, api_key=api_key)
        case "openai":
            from .openai_client import OpenAIClient
            return OpenAIClient(model=model, api_key=api_key)
        case "local":
            from .local_client import LocalClient
            return LocalClient(model=model)
        case _:
            raise ValueError(
                f"Unknown provider {provider!r}. Choose: anthropic, openai, local"
            )
