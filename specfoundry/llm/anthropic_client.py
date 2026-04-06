"""Anthropic (Claude) LLM adapter."""
from __future__ import annotations

import os
import time
from typing import Iterator

import anthropic

from .base import LLMClient, Message

_DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


class AnthropicClient(LLMClient):
    def __init__(self, model: str = _DEFAULT_MODEL, api_key: str | None = None):
        self.model = model
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    def generate(
        self,
        messages: list[Message],
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        kwargs = self._build_kwargs(messages, system, max_tokens, temperature)
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.messages.create(**kwargs)
                return resp.content[0].text
            except anthropic.RateLimitError as exc:
                last_exc = exc
                time.sleep(_BACKOFF_BASE ** attempt)
            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500:
                    last_exc = exc
                    time.sleep(_BACKOFF_BASE ** attempt)
                else:
                    raise
        raise last_exc  # type: ignore[misc]

    def stream(
        self,
        messages: list[Message],
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> Iterator[str]:
        kwargs = self._build_kwargs(messages, system, max_tokens, temperature)
        with self._client.messages.stream(**kwargs) as stream:
            yield from stream.text_stream

    def _build_kwargs(
        self,
        messages: list[Message],
        system: str,
        max_tokens: int,
        temperature: float,
    ) -> dict:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system
        return kwargs
