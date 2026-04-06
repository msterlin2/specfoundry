"""Local model adapter (Ollama-compatible HTTP API)."""
from __future__ import annotations

import json
from typing import Iterator
from urllib.request import urlopen, Request

from .base import LLMClient, Message

_DEFAULT_BASE_URL = "http://localhost:11434"


class LocalClient(LLMClient):
    """Connects to an Ollama-compatible local server.

    Set OLLAMA_BASE_URL env var or pass base_url to override the endpoint.
    """

    def __init__(self, model: str = "llama3", base_url: str = _DEFAULT_BASE_URL):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        messages: list[Message],
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        payload = self._build_payload(messages, system, stream=False)
        req = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        return data.get("message", {}).get("content", "")

    def stream(
        self,
        messages: list[Message],
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> Iterator[str]:
        payload = self._build_payload(messages, system, stream=True)
        req = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=120) as resp:
            for line in resp:
                chunk = json.loads(line)
                if content := chunk.get("message", {}).get("content"):
                    yield content
                if chunk.get("done"):
                    break

    def _build_payload(
        self, messages: list[Message], system: str, stream: bool
    ) -> dict:
        api_messages = []
        if system:
            api_messages.append({"role": "system", "content": system})
        api_messages.extend({"role": m.role, "content": m.content} for m in messages)
        return {"model": self.model, "messages": api_messages, "stream": stream}
