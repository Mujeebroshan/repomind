"""Knowledge base for hierarchical codebase understanding.

Stores LLM-generated summaries at four levels:
1. File — purpose, key symbols, dependencies
2. Directory — how files interact, module role
3. Component — group of related directories
4. Project — architecture, tech stack, patterns

Persisted as JSON in .repomind/knowledge_base.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class KnowledgeBase:
    """In-memory knowledge store with JSON persistence."""

    def __init__(self):
        self.file_summaries: dict[str, dict] = {}
        self.directory_summaries: dict[str, dict] = {}
        self.component_summaries: dict[str, dict] = {}
        self.project_overview: dict = {}
        self.patterns: list[dict] = []
        self.file_mtimes: dict[str, float] = {}
        self.last_analyzed: str = ""

    # ── Setters ────────────────────────────────────────────────────────

    def set_file_summary(self, path: str, summary: str, language: str = "",
                         functions: list[str] | None = None,
                         classes: list[str] | None = None,
                         imports: list[str] | None = None,
                         line_count: int = 0) -> None:
        self.file_summaries[path] = {
            "path": path, "summary": summary, "language": language,
            "functions": functions or [], "classes": classes or [],
            "imports": imports or [], "line_count": line_count,
        }

    def set_directory_summary(self, path: str, summary: str, purpose: str = "",
                              files: list[str] | None = None,
                              subdirectories: list[str] | None = None) -> None:
        self.directory_summaries[path] = {
            "path": path, "summary": summary, "purpose": purpose,
            "files": files or [], "subdirectories": subdirectories or [],
        }

    def set_project_overview(self, name: str = "", summary: str = "",
                             architecture: str = "",
                             tech_stack: list[str] | None = None,
                             components: list[str] | None = None,
                             patterns: list[str] | None = None,
                             entry_points: list[str] | None = None) -> None:
        self.project_overview = {
            "name": name, "summary": summary, "architecture": architecture,
            "tech_stack": tech_stack or [], "components": components or [],
            "patterns": patterns or [], "entry_points": entry_points or [],
        }

    # ── Getters ────────────────────────────────────────────────────────

    def get_file_summary(self, path: str) -> Optional[dict]:
        return self.file_summaries.get(path)

    def get_directory_summary(self, path: str) -> Optional[dict]:
        return self.directory_summaries.get(path)

    def get_project_overview(self) -> dict:
        return self.project_overview

    # ── Staleness ──────────────────────────────────────────────────────

    def get_stale_files(self, repo_root: Path,
                        current_files: list[Path]) -> list[str]:
        """Files that changed since last analysis."""
        stale: list[str] = []
        for fp in current_files:
            rel = str(fp.relative_to(repo_root))
            try:
                mtime = fp.stat().st_mtime
            except OSError:
                continue
            prev = self.file_mtimes.get(rel, 0)
            if mtime > prev or rel not in self.file_summaries:
                stale.append(rel)
        return stale

    def record_mtime(self, repo_root: Path, rel_path: str) -> None:
        try:
            self.file_mtimes[rel_path] = (repo_root / rel_path).stat().st_mtime
        except OSError:
            pass

    # ── Context helpers ────────────────────────────────────────────────

    def get_context_for_path(self, path: str) -> str:
        """Aggregate file + parent dir + project summaries into text."""
        parts: list[str] = []
        fs = self.file_summaries.get(path)
        if fs:
            parts.append(f"[File: {path}] {fs.get('summary', '')}")
        parent = str(Path(path).parent)
        ds = self.directory_summaries.get(parent)
        if ds:
            parts.append(f"[Directory: {parent}] {ds.get('summary', '')}")
        if self.project_overview:
            parts.append(f"[Project] {self.project_overview.get('summary', '')[:300]}")
        return "\n".join(parts)

    def search_summaries(self, query: str) -> list[dict]:
        """Simple keyword search across all summaries."""
        q = query.lower()
        results: list[dict] = []
        for s in self.file_summaries.values():
            if q in s.get("summary", "").lower() or q in s.get("path", "").lower():
                results.append(s)
        for s in self.directory_summaries.values():
            if q in s.get("summary", "").lower() or q in s.get("path", "").lower():
                results.append(s)
        return results

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "file_summaries": self.file_summaries,
            "directory_summaries": self.directory_summaries,
            "component_summaries": self.component_summaries,
            "project_overview": self.project_overview,
            "patterns": self.patterns,
            "file_mtimes": self.file_mtimes,
            "last_analyzed": self.last_analyzed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeBase":
        kb = cls()
        kb.file_summaries = data.get("file_summaries", {})
        kb.directory_summaries = data.get("directory_summaries", {})
        kb.component_summaries = data.get("component_summaries", {})
        kb.project_overview = data.get("project_overview", {})
        kb.patterns = data.get("patterns", [])
        kb.file_mtimes = data.get("file_mtimes", {})
        kb.last_analyzed = data.get("last_analyzed", "")
        return kb

    def save(self, repo_root: Path) -> None:
        d = repo_root / ".repomind"
        d.mkdir(parents=True, exist_ok=True)
        (d / "knowledge_base.json").write_text(
            json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        self.last_analyzed = datetime.now(timezone.utc).isoformat()

    @classmethod
    def load(cls, repo_root: Path) -> "KnowledgeBase":
        p = repo_root / ".repomind" / "knowledge_base.json"
        if p.exists():
            try:
                return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
        return cls()
