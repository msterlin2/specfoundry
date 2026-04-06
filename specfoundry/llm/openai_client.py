"""OpenAI LLM adapter."""
from __future__ import annotations

import os
import time
from typing import Iterator

import openai

from .base import LLMClient, Message

_DEFAULT_MODEL = "gpt-4o"
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


class OpenAIClient(LLMClient):
    def __init__(self, model: str = _DEFAULT_MODEL, api_key: str | None = None):
        self.model = model
        self._client = openai.OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY")
        )

    def generate(
        self,
        messages: list[Message],
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        api_msgs = self._build_messages(messages, system)
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=api_msgs,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return resp.choices[0].message.content or ""
            except openai.RateLimitError as exc:
                last_exc = exc
                time.sleep(_BACKOFF_BASE ** attempt)
            except openai.APIStatusError as exc:
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
        api_msgs = self._build_messages(messages, system)
        with self._client.chat.completions.stream(
            model=self.model,
            messages=api_msgs,
            max_tokens=max_tokens,
            temperature=temperature,
        ) as stream:
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    def _build_messages(self, messages: list[Message], system: str) -> list[dict]:
        result = []
        if system:
            result.append({"role": "system", "content": system})
        result.extend({"role": m.role, "content": m.content} for m in messages)
        return result
