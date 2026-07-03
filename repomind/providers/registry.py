from __future__ import annotations

from ..config import WorkspaceSettings
from .anthropic_provider import AnthropicProvider
from .base import Provider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider
from .openai_compatible import GroqProvider, LMStudioProvider, OpenAIProvider, OpenRouterProvider

FRONTIER_PROVIDER_CLASSES = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "openrouter": OpenRouterProvider,
}


def build_local_provider(settings: WorkspaceSettings):
    """Returns whichever local backend is configured -- Ollama or LM
    Studio -- as an object exposing chat_stream() and embed(). The rest
    of the app (router, indexer, chat engine) just calls those two
    methods and never needs to know which one it got.
    """
    if settings.local_backend == "lmstudio":
        provider = LMStudioProvider(model=settings.local_chat_model, base_url=settings.lmstudio_host)
    else:
        provider = OllamaProvider(model=settings.local_chat_model, base_url=settings.ollama_host)
    provider.embed_model = settings.local_embed_model
    return provider


def build_frontier_provider(provider_id: str, settings: WorkspaceSettings) -> Provider:
    if provider_id not in FRONTIER_PROVIDER_CLASSES:
        raise ValueError(f"Unknown provider: {provider_id}")
    cfg = settings.providers.get(provider_id)
    cls = FRONTIER_PROVIDER_CLASSES[provider_id]
    if cfg is None:
        return cls()
    kwargs = {"api_key": cfg.api_key, "model": cfg.model or cls().model}
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    return cls(**kwargs)


def list_provider_statuses(settings: WorkspaceSettings) -> list[dict]:
    statuses = []
    for pid, cls in FRONTIER_PROVIDER_CLASSES.items():
        provider = build_frontier_provider(pid, settings)
        statuses.append(
            {
                "id": pid,
                "display_name": provider.display_name,
                "configured": provider.is_configured(),
                "model": provider.model,
            }
        )
    return statuses
