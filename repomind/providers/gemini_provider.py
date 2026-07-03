from __future__ import annotations

from typing import AsyncIterator, Optional

import httpx

from .base import ChatMessage, Provider, ProviderError


class GeminiProvider(Provider):
    id = "gemini"
    display_name = "Gemini (Google)"

    def __init__(self, api_key: str = "", model: str = "gemini-3.5-flash", base_url: Optional[str] = None):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=(base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/"),
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        if not self.is_configured():
            raise ProviderError("Gemini is not configured. Add a Gemini API key in Settings.")

        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        body: dict = {"contents": contents, "generationConfig": {"temperature": temperature}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code != 200:
                raise ProviderError(f"Gemini returned {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise ProviderError("Gemini returned no candidates (the response may have been blocked).")
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            # Non-streaming for now: yield the whole answer as a single chunk.
            # (Gemini's streamGenerateContent uses SSE too, but with a
            # different envelope -- worth adding once v1 ships.)
            yield text
