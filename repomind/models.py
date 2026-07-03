from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class OpenWorkspaceRequest(BaseModel):
    repo_path: str


class IndexRequest(BaseModel):
    repo_path: str
    force: bool = False


class IndexStatus(BaseModel):
    state: Literal["idle", "scanning", "embedding", "done", "error"] = "idle"
    files_total: int = 0
    files_done: int = 0
    chunks_indexed: int = 0
    error: Optional[str] = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    repo_path: str
    question: str
    history: list[ChatTurn] = []
    mode: Literal["auto", "local_only", "escalate_only"] = "auto"


class StatsResponse(BaseModel):
    local_count: int = 0
    escalated_count: int = 0
    estimated_cloud_cost_usd: float = 0.0
    estimated_savings_usd: float = 0.0


class ProviderStatus(BaseModel):
    id: str
    display_name: str
    configured: bool
    model: str


class SettingsResponse(BaseModel):
    ollama_host: str
    lmstudio_host: str
    local_backend: str
    local_chat_model: str
    local_embed_model: str
    default_mode: str
    default_escalation_provider: str
    providers: dict[str, dict]


class SettingsUpdateRequest(BaseModel):
    ollama_host: Optional[str] = None
    lmstudio_host: Optional[str] = None
    local_backend: Optional[str] = None
    local_chat_model: Optional[str] = None
    local_embed_model: Optional[str] = None
    default_mode: Optional[str] = None
    default_escalation_provider: Optional[str] = None
    # provider_id -> {"api_key": "...", "model": "..."} ; omit api_key to leave it unchanged
    providers: Optional[dict[str, dict]] = None


# ── Understanding pipeline models ────────────────────────────────────

class AnalyzeRequest(BaseModel):
    repo_path: str
    force: bool = False
    depth: str = "standard"  # quick | standard | deep


class AnalyzeStatus(BaseModel):
    state: str = "idle"
    phase: str = ""
    files_total: int = 0
    files_done: int = 0
    directories_total: int = 0
    directories_done: int = 0
    error: str = ""


class KnowledgeQuery(BaseModel):
    repo_path: str
    level: str = "project"
    path: str = ""


class GenerateRequest(BaseModel):
    repo_path: str
    description: str
    target_path: str = ""
    mode: str = "code"  # code | scaffold | suggestion
