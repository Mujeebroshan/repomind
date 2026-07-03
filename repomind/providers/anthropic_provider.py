from __future__ import annotations

import json
from typing import AsyncIterator, Optional

import httpx

from .base import ChatMessage, Provider, ProviderError

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    id = "anthropic"
    display_name = "Claude (Anthropic)"

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-6", base_url: Optional[str] = None):
        super().__init__(api_key=api_key, model=model, base_url=(base_url or "https://api.anthropic.com").rstrip("/"))

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        if not self.is_configured():
            raise ProviderError("Claude is not configured. Add an Anthropic API key in Settings.")

        body = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "stream": True,
        }
        if system:
            body["system"] = system

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        url = f"{self.base_url}/v1/messages"
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    text = await resp.aread()
                    raise ProviderError(f"Claude API returned {resp.status_code}: {text.decode(errors='ignore')[:300]}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")
