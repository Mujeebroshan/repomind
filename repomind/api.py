"""API endpoints for RepoMind."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from . import chat_engine
from .config import load_settings, mask_key, save_settings
from .indexer import get_index_status, has_index, index_repo
from .models import (
    AnalyzeRequest,
    AnalyzeStatus,
    ChatRequest,
    GenerateRequest,
    IndexRequest,
    IndexStatus,
    OpenWorkspaceRequest,
    SettingsResponse,
    SettingsUpdateRequest,
    StatsResponse,
)
from .providers.registry import list_provider_statuses, build_local_provider
from .stats import load_stats

router = APIRouter(prefix="/api")


def _resolve_repo(repo_path: str) -> Path:
    p = Path(repo_path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=400, detail=f"{p} is not a directory that exists.")
    return p


# ── Workspace ────────────────────────────────────────────────────────

@router.post("/workspace")
async def open_workspace(req: OpenWorkspaceRequest):
    repo = _resolve_repo(req.repo_path)
    settings = load_settings(repo)
    # Check if analysis exists
    analyzed = False
    try:
        from .understanding.knowledge_base import KnowledgeBase
        kb = KnowledgeBase.load(repo)
        analyzed = bool(kb.project_overview)
    except Exception:
        pass
    return {
        "repo_path": str(repo),
        "indexed": has_index(repo),
        "analyzed": analyzed,
        "settings": _settings_to_response(settings).model_dump(),
    }


# ── Indexing ─────────────────────────────────────────────────────────

@router.post("/index", response_model=IndexStatus)
async def start_index(req: IndexRequest):
    repo = _resolve_repo(req.repo_path)
    if has_index(repo) and not req.force:
        status = get_index_status(repo)
        if status.state == "done":
            return status
    settings = load_settings(repo)
    asyncio.create_task(index_repo(repo, settings))
    return IndexStatus(state="scanning")


@router.get("/index/status", response_model=IndexStatus)
async def index_status(repo_path: str):
    repo = _resolve_repo(repo_path)
    return get_index_status(repo)


# ── Chat ─────────────────────────────────────────────────────────────

@router.post("/chat")
async def chat(req: ChatRequest):
    repo = _resolve_repo(req.repo_path)
    settings = load_settings(repo)

    async def event_stream():
        try:
            async for event in chat_engine.run_chat(repo, settings, req.question, req.history, req.mode):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Stats ────────────────────────────────────────────────────────────

@router.get("/stats", response_model=StatsResponse)
async def stats(repo_path: str):
    repo = _resolve_repo(repo_path)
    return load_stats(repo)


# ── Analysis ─────────────────────────────────────────────────────────

@router.post("/analyze")
async def start_analyze(req: AnalyzeRequest):
    """Start the deep understanding pipeline."""
    repo = _resolve_repo(req.repo_path)
    settings = load_settings(repo)
    from .understanding.analyzer import analyze_repo, get_analyze_status
    current = get_analyze_status(repo)
    if current.state not in ("idle", "done", "error") and not req.force:
        return current.model_dump() if hasattr(current, "model_dump") else current.__dict__
    asyncio.create_task(analyze_repo(repo, settings, depth=req.depth))
    return {"state": "scanning", "phase": "Starting analysis..."}


@router.get("/analyze/status")
async def analyze_status(repo_path: str):
    repo = _resolve_repo(repo_path)
    from .understanding.analyzer import get_analyze_status
    status = get_analyze_status(repo)
    return status.__dict__ if not hasattr(status, "model_dump") else status.model_dump()


# ── Knowledge Base ───────────────────────────────────────────────────

@router.get("/knowledge")
async def get_knowledge(repo_path: str, level: str = "project", path: str = ""):
    """Query the knowledge base at a given level."""
    repo = _resolve_repo(repo_path)
    from .understanding.knowledge_base import KnowledgeBase
    kb = KnowledgeBase.load(repo)

    if level == "project":
        overview = kb.get_project_overview()
        return {
            "level": "project",
            "data": overview,
            "patterns": kb.patterns[:20],
            "file_count": len(kb.file_summaries),
            "dir_count": len(kb.directory_summaries),
            "last_analyzed": kb.last_analyzed,
        }
    elif level == "directory":
        ds = kb.get_directory_summary(path)
        return {"level": "directory", "path": path, "data": ds or {}}
    elif level == "file":
        fs = kb.get_file_summary(path)
        return {"level": "file", "path": path, "data": fs or {}}
    elif level == "search":
        results = kb.search_summaries(path)  # use 'path' as query
        return {"level": "search", "query": path, "results": results[:20]}
    else:
        return {"level": level, "data": {}}


# ── Dependency Graph ─────────────────────────────────────────────────

@router.get("/graph")
async def get_graph(repo_path: str):
    repo = _resolve_repo(repo_path)
    from .graph.builder import DependencyGraph
    graph = DependencyGraph.load(repo)
    data = graph.to_dict()
    return {"nodes": len(data.get("nodes", [])),
            "edges": len(data.get("edges", [])),
            "data": data}


# ── Repo Map ─────────────────────────────────────────────────────────

@router.get("/repomap")
async def get_repomap(repo_path: str):
    repo = _resolve_repo(repo_path)
    from .retrieval.repo_map import generate_repo_map
    repo_map = generate_repo_map(repo)
    return {"map": repo_map}


# ── Code Generation ──────────────────────────────────────────────────

@router.post("/generate/code")
async def generate_code_endpoint(req: GenerateRequest):
    repo = _resolve_repo(req.repo_path)
    settings = load_settings(repo)
    from .generation.code_generator import generate_code
    provider = build_local_provider(settings)
    result = await generate_code(repo, provider, req.description, req.target_path)
    return result


# ── Suggestions ──────────────────────────────────────────────────────

@router.get("/suggestions")
async def get_suggestions(repo_path: str):
    repo = _resolve_repo(repo_path)
    settings = load_settings(repo)
    from .generation.suggestions import generate_suggestions
    provider = build_local_provider(settings)
    suggestions = await generate_suggestions(repo, provider)
    return {"suggestions": suggestions}


# ── Settings ─────────────────────────────────────────────────────────

def _settings_to_response(settings) -> SettingsResponse:
    provider_statuses = list_provider_statuses(settings)
    providers_out = {}
    for s in provider_statuses:
        cfg = settings.providers.get(s["id"])
        providers_out[s["id"]] = {
            "display_name": s["display_name"],
            "configured": s["configured"],
            "model": s["model"],
            "api_key_preview": mask_key(cfg.api_key) if cfg else "",
        }
    return SettingsResponse(
        ollama_host=settings.ollama_host,
        lmstudio_host=settings.lmstudio_host,
        local_backend=settings.local_backend,
        local_chat_model=settings.local_chat_model,
        local_embed_model=settings.local_embed_model,
        default_mode=settings.default_mode,
        default_escalation_provider=settings.default_escalation_provider,
        providers=providers_out,
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(repo_path: str):
    repo = _resolve_repo(repo_path)
    settings = load_settings(repo)
    return _settings_to_response(settings)


@router.post("/settings", response_model=SettingsResponse)
async def update_settings(repo_path: str, req: SettingsUpdateRequest):
    repo = _resolve_repo(repo_path)
    settings = load_settings(repo)

    if req.ollama_host is not None:
        settings.ollama_host = req.ollama_host
    if req.lmstudio_host is not None:
        settings.lmstudio_host = req.lmstudio_host
    if req.local_backend is not None:
        settings.local_backend = req.local_backend
    if req.local_chat_model is not None:
        settings.local_chat_model = req.local_chat_model
    if req.local_embed_model is not None:
        settings.local_embed_model = req.local_embed_model
    if req.default_mode is not None:
        settings.default_mode = req.default_mode
    if req.default_escalation_provider is not None:
        settings.default_escalation_provider = req.default_escalation_provider
    if req.providers:
        for pid, values in req.providers.items():
            cfg = settings.providers.get(pid)
            if cfg is None:
                continue
            if values.get("api_key"):
                cfg.api_key = values["api_key"]
            if values.get("model"):
                cfg.model = values["model"]
            if "base_url" in values:
                cfg.base_url = values["base_url"] or None

    save_settings(repo, settings)
    return _settings_to_response(settings)


@router.get("/health")
async def health():
    return {"ok": True}
