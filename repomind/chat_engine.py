from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Literal

from . import router
from .config import WorkspaceSettings
from .indexer import get_collection, has_index
from .models import ChatTurn
from .providers.base import ChatMessage, ProviderError
from .providers.ollama_provider import OllamaProvider
from .providers.registry import build_frontier_provider, build_local_provider
from .stats import record_exchange

TOP_K = 6

ANSWER_SYSTEM_PROMPT = """You are a codebase assistant. Answer using only the \
code snippets provided as context below -- they were retrieved from the \
user's own repository. If the snippets don't contain enough information to \
answer confidently, say so plainly rather than guessing. Reference file \
paths and line numbers when it helps the user locate something. Be direct \
and avoid restating the question."""


def _format_context(results) -> tuple[str, list[str]]:
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    blocks = []
    files = []
    for doc, meta in zip(docs, metas):
        file_path = meta.get("file_path", "?")
        start = meta.get("start_line", "?")
        end = meta.get("end_line", "?")
        files.append(file_path)
        blocks.append(f"--- {file_path} (lines {start}-{end}) ---\n{doc}")
    return "\n\n".join(blocks), files


async def run_chat(
    repo_root: Path,
    settings: WorkspaceSettings,
    question: str,
    history: list[ChatTurn],
    mode: Literal["auto", "local_only", "escalate_only"],
) -> AsyncIterator[dict]:
    if not has_index(repo_root):
        yield {"type": "error", "message": "This repo hasn't been indexed yet. Click Index in the sidebar first."}
        return

    local = build_local_provider(settings)

    # 1. Retrieval is always local: the full codebase never leaves the machine.
    try:
        query_vector = (await local.embed([question]))[0]
    except ProviderError as exc:
        yield {"type": "error", "message": f"Retrieval needs Ollama for embeddings. {exc}"}
        return

    collection = get_collection(repo_root)
    results = collection.query(query_embeddings=[query_vector], n_results=TOP_K)
    context, files = _format_context(results)

    # 2. Decide who answers.
    used_local_router = False
    if mode == "local_only":
        route = "local"
    elif mode == "escalate_only":
        route = "escalate"
    else:
        verdict, used_local_router = await router.classify(local, question, files)
        route = "local" if verdict == "SIMPLE" else "escalate"

    yield {"type": "route", "route": route, "router_was_local": used_local_router, "files": files}

    messages: list[ChatMessage] = [{"role": t.role, "content": t.content} for t in history]
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"})

    provider_id = "ollama"
    provider_label = local.display_name
    try:
        if route == "local":
            provider = local
        else:
            provider_id = settings.default_escalation_provider
            provider = build_frontier_provider(provider_id, settings)
            if not provider.is_configured():
                # Graceful degrade: no escalation provider configured, answer locally instead and say so.
                yield {
                    "type": "notice",
                    "message": f"{provider.display_name} isn't configured -- answering locally instead.",
                }
                provider = local
                route = "local"
            else:
                provider_label = provider.display_name

        full_text = []
        async for piece in provider.chat_stream(messages, system=ANSWER_SYSTEM_PROMPT, temperature=0.2):
            full_text.append(piece)
            yield {"type": "token", "text": piece}

        stats = record_exchange(repo_root, escalated=(route == "escalate"))
        yield {
            "type": "done",
            "route": route,
            "provider": provider_id if route == "escalate" else "ollama",
            "provider_label": provider_label,
            "local_count": stats.local_count,
            "escalated_count": stats.escalated_count,
            "estimated_savings_usd": round(stats.estimated_savings_usd, 4),
        }
    except ProviderError as exc:
        yield {"type": "error", "message": str(exc)}
