"""Configuration.

Two layers, deliberately kept separate:

1. EnvDefaults -- read once from the process environment / .env file.
   These are fallbacks: things like OLLAMA_HOST or an API key you'd
   rather not type into a browser form every time.

2. WorkspaceSettings -- a small JSON file living at <repo>/.repomind/settings.json.
   This is what the Settings panel in the UI actually edits. It is
   per-repo on purpose: different projects may warrant different
   escalation providers (e.g. a client's private repo might be
   "local only", a side project might escalate to Claude freely).

Workspace settings override env defaults field-by-field. API keys are
never round-tripped to the browser in full -- only a masked preview.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROVIDER_IDS = ["anthropic", "openai", "gemini", "groq", "openrouter"]

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4.1",
    "gemini": "gemini-3.5-flash",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "anthropic/claude-sonnet-4-6",
}


class EnvDefaults(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    lmstudio_host: str = Field(default="http://localhost:1234/v1", alias="LMSTUDIO_HOST")
    local_backend: str = Field(default="ollama", alias="LOCAL_BACKEND")  # "ollama" | "lmstudio"
    local_chat_model: str = Field(default="qwen2.5-coder:7b", alias="LOCAL_CHAT_MODEL")
    local_embed_model: str = Field(default="nomic-embed-text", alias="LOCAL_EMBED_MODEL")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")

    default_escalation_provider: str = Field(default="gemini", alias="DEFAULT_ESCALATION_PROVIDER")
    analysis_depth: str = Field(default="standard", alias="ANALYSIS_DEPTH")
    max_concurrent_summaries: int = Field(default=4, alias="MAX_CONCURRENT_SUMMARIES")
    use_cloud_for_project_summary: bool = Field(default=True, alias="USE_CLOUD_FOR_PROJECT_SUMMARY")


class ProviderConfig(BaseModel):
    api_key: str = ""
    model: str = ""
    base_url: Optional[str] = None


class WorkspaceSettings(BaseModel):
    ollama_host: str = "http://localhost:11434"
    lmstudio_host: str = "http://localhost:1234/v1"
    local_backend: str = "ollama"  # "ollama" | "lmstudio"
    local_chat_model: str = "qwen2.5-coder:7b"
    local_embed_model: str = "nomic-embed-text"
    default_mode: str = "auto"  # auto | local_only | escalate_only
    default_escalation_provider: str = "gemini"
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    analysis_depth: str = "standard"  # quick | standard | deep
    summary_model: str = ""  # override model for summaries; empty = use local_chat_model
    max_concurrent_summaries: int = 4
    use_cloud_for_project_summary: bool = True
    generation_provider: str = "auto"  # auto | local_only | <provider_id>

    @classmethod
    def from_env(cls, env: EnvDefaults) -> "WorkspaceSettings":
        providers = {
            "anthropic": ProviderConfig(api_key=env.anthropic_api_key, model=DEFAULT_MODELS["anthropic"]),
            "openai": ProviderConfig(api_key=env.openai_api_key, model=DEFAULT_MODELS["openai"]),
            "gemini": ProviderConfig(api_key=env.gemini_api_key, model=DEFAULT_MODELS["gemini"]),
            "groq": ProviderConfig(api_key=env.groq_api_key, model=DEFAULT_MODELS["groq"]),
            "openrouter": ProviderConfig(api_key=env.openrouter_api_key, model=DEFAULT_MODELS["openrouter"]),
        }
        return cls(
            ollama_host=env.ollama_host,
            lmstudio_host=env.lmstudio_host,
            local_backend=env.local_backend,
            local_chat_model=env.local_chat_model,
            local_embed_model=env.local_embed_model,
            default_escalation_provider=env.default_escalation_provider,
            providers=providers,
            analysis_depth=env.analysis_depth,
            max_concurrent_summaries=env.max_concurrent_summaries,
            use_cloud_for_project_summary=env.use_cloud_for_project_summary,
        )


def workspace_data_dir(repo_path: Path) -> Path:
    d = repo_path / ".repomind"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_settings(repo_path: Path) -> WorkspaceSettings:
    settings_path = workspace_data_dir(repo_path) / "settings.json"
    env = EnvDefaults()
    if settings_path.exists():
        try:
            raw = json.loads(settings_path.read_text())
            return WorkspaceSettings.model_validate(raw)
        except Exception:
            pass  # fall through to fresh defaults rather than crash the app
    settings = WorkspaceSettings.from_env(env)
    save_settings(repo_path, settings)
    return settings


def save_settings(repo_path: Path, settings: WorkspaceSettings) -> None:
    settings_path = workspace_data_dir(repo_path) / "settings.json"
    settings_path.write_text(settings.model_dump_json(indent=2))


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"
