from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, TypedDict


class ChatMessage(TypedDict):
    role: str  # "user" | "assistant"
    content: str


class Provider(ABC):
    """A chat backend -- either a local model served by Ollama/LM Studio,
    or a frontier API. Every provider exposes the same streaming surface
    so the router and chat engine never need to know which one they're
    talking to.
    """

    id: str = "base"
    display_name: str = "Base"

    def __init__(self, api_key: str = "", model: str = "", base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @abstractmethod
    def chat_stream(
        self,
        messages: list[ChatMessage],
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """Yield response text incrementally. Implementations are async generators."""
        raise NotImplementedError


async def complete(provider: Provider, messages: list[ChatMessage], system: Optional[str] = None, temperature: float = 0.2) -> str:
    """Convenience helper: drain a provider's stream into a single string.
    Used for the router's classification call, where we just need one short word back.
    """
    chunks = []
    async for piece in provider.chat_stream(messages, system=system, temperature=temperature):
        chunks.append(piece)
    return "".join(chunks)


class ProviderError(RuntimeError):
    """Raised when a provider can't be reached or returns an error we should
    surface to the user in plain language rather than a stack trace.
    """
