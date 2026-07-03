from __future__ import annotations

import json
from typing import AsyncIterator, Optional

import httpx

from .base import ChatMessage, Provider, ProviderError


class OpenAICompatibleProvider(Provider):
    """Base class for any provider speaking the OpenAI chat/completions
    dialect: POST {base_url}/chat/completions, Bearer auth, SSE stream of
    {"choices": [{"delta": {"content": "..."}}]} chunks ending in [DONE].
    OpenAI, Groq, and OpenRouter all implement this, which is why this
    one class backs all three.
    """

    id = "openai_compatible"
    display_name = "OpenAI-compatible"
    extra_headers: dict[str, str] = {}

    def __init__(self, api_key: str = "", model: str = "", base_url: str = ""):
        super().__init__(api_key=api_key, model=model, base_url=base_url.rstrip("/"))

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        if not self.is_configured():
            raise ProviderError(f"{self.display_name} is not configured. Add an API key in Settings.")

        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend({"role": m["role"], "content": m["content"]} for m in messages)

        body = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": temperature,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **self.extra_headers}
        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    text = await resp.aread()
                    raise ProviderError(
                        f"{self.display_name} returned {resp.status_code}: {text.decode(errors='ignore')[:300]}"
                    )
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    piece = delta.get("content")
                    if piece:
                        yield piece


class OpenAIProvider(OpenAICompatibleProvider):
    id = "openai"
    display_name = "OpenAI"

    def __init__(self, api_key: str = "", model: str = "gpt-4.1", base_url: Optional[str] = None):
        super().__init__(api_key=api_key, model=model, base_url=base_url or "https://api.openai.com/v1")


class GroqProvider(OpenAICompatibleProvider):
    id = "groq"
    display_name = "Groq"

    def __init__(self, api_key: str = "", model: str = "llama-3.3-70b-versatile", base_url: Optional[str] = None):
        super().__init__(api_key=api_key, model=model, base_url=base_url or "https://api.groq.com/openai/v1")


class OpenRouterProvider(OpenAICompatibleProvider):
    id = "openrouter"
    display_name = "OpenRouter"
    extra_headers = {"HTTP-Referer": "https://github.com/", "X-Title": "repomind"}

    def __init__(self, api_key: str = "", model: str = "anthropic/claude-sonnet-4-6", base_url: Optional[str] = None):
        super().__init__(api_key=api_key, model=model, base_url=base_url or "https://openrouter.ai/api/v1")


class LMStudioProvider(OpenAICompatibleProvider):
    """LM Studio's local server is OpenAI-compatible for both chat and
    embeddings, so this is the OpenAI-compatible base pointed at localhost
    with a dummy key, plus an embeddings call so it can be used as a full
    local backend (chat + retrieval) just like the Ollama provider.
    """

    id = "lmstudio"
    display_name = "LM Studio (local)"

    def __init__(self, model: str = "local-model", base_url: str = "http://localhost:1234/v1"):
        super().__init__(api_key="lm-studio", model=model, base_url=base_url)

    def is_configured(self) -> bool:
        return True

    async def embed(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {"model": self.embed_model, "input": texts}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                raise ProviderError(f"LM Studio embeddings returned {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            return [item["embedding"] for item in data["data"]]

    @property
    def embed_model(self) -> str:
        return getattr(self, "_embed_model", self.model)

    @embed_model.setter
    def embed_model(self, value: str) -> None:
        self._embed_model = value
