from __future__ import annotations

import hashlib
import math
from typing import AsyncIterator, Optional

from codechat.providers.base import ChatMessage, Provider
from codechat.providers.ollama_provider import OllamaProvider


def bow_embed(text: str, dims: int = 32) -> list[float]:
    """A deterministic bag-of-words embedding -- not semantically meaningful,
    but enough to make retrieval tests behave predictably without needing a
    real embedding model.
    """
    vec = [0.0] * dims
    for word in text.lower().split():
        idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % dims
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeOllamaProvider(OllamaProvider):
    """Stands in for a local Ollama server. Returns `route_reply` when asked
    to classify (system prompt mentions "routing classifier") and
    `answer_reply` otherwise, so router and answer-generation calls can be
    asserted on independently even though they share one object.
    """

    def __init__(self, model: str = "fake-local", base_url: str = "http://fake", route_reply: str = "SIMPLE", answer_reply: str = "local answer"):
        super().__init__(model=model, base_url=base_url)
        self.route_reply = route_reply
        self.answer_reply = answer_reply
        self.embed_model = "fake-embed"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [bow_embed(t) for t in texts]

    async def chat_stream(
        self, messages: list[ChatMessage], system: Optional[str] = None, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        if system and "routing classifier" in system.lower():
            yield self.route_reply
        else:
            yield self.answer_reply


class FakeFrontierProvider(Provider):
    id = "fake_frontier"
    display_name = "Fake Frontier"

    def __init__(self, reply: str = "cloud answer", configured: bool = True):
        super().__init__(api_key=("key" if configured else ""), model="fake-model")
        self.reply = reply

    async def chat_stream(
        self, messages: list[ChatMessage], system: Optional[str] = None, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        yield self.reply
