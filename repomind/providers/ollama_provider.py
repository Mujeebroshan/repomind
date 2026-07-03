from __future__ import annotations

import json
from typing import AsyncIterator, Optional

import httpx

from .base import ChatMessage, Provider, ProviderError


class OllamaProvider(Provider):
    """Talks to a local Ollama server. No API key needed -- "configured"
    just means "we have a host to try"; actual reachability is checked
    lazily on first call so the app can still start up if Ollama isn't
    running yet.
    """

    id = "ollama"
    display_name = "Ollama (local)"

    def __init__(self, model: str = "qwen2.5-coder:7b", base_url: str = "http://localhost:11434"):
        super().__init__(api_key="local", model=model, base_url=base_url.rstrip("/"))

    def is_configured(self) -> bool:
        return True

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)

        body = {
            "model": self.model,
            "messages": payload_messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        url = f"{self.base_url}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", url, json=body) as resp:
                    if resp.status_code != 200:
                        text = await resp.aread()
                        raise ProviderError(
                            f"Ollama returned {resp.status_code}: {text.decode(errors='ignore')[:300]}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        if chunk.get("done"):
                            break
                        piece = chunk.get("message", {}).get("content", "")
                        if piece:
                            yield piece
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Couldn't reach Ollama at {self.base_url}. Is it running? (ollama serve)"
            ) from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/api/embed"
        body = {"model": self.embed_model, "input": texts}
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body)
                if resp.status_code != 200:
                    raise ProviderError(
                        f"Ollama embeddings returned {resp.status_code}: {resp.text[:300]}"
                    )
                data = resp.json()
                return data["embeddings"]
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Couldn't reach Ollama at {self.base_url} for embeddings. Is it running?"
            ) from exc

    @property
    def embed_model(self) -> str:
        return getattr(self, "_embed_model", "nomic-embed-text")

    @embed_model.setter
    def embed_model(self, value: str) -> None:
        self._embed_model = value

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
