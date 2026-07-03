"""Main analysis pipeline orchestrator.

Coordinates the full understanding pipeline:
1. Discover files
2. AST parse all files
3. Build dependency graph
4. Generate file summaries (with parent directory context)
5. Generate directory summaries
6. Generate project overview
7. Extract patterns
8. Save knowledge base

Reports progress via a status dict for SSE streaming to the frontend.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..config import WorkspaceSettings
from ..models import AnalyzeStatus
from ..chunking import discover_files
from ..parser.ast_parser import parse_file, parse_repo, FileStructure
from ..graph.builder import DependencyGraph
from ..providers.registry import build_local_provider, build_frontier_provider
from .knowledge_base import KnowledgeBase
from .summarizer import summarize_file, summarize_directory, summarize_project
from .pattern_extractor import extract_patterns

logger = logging.getLogger(__name__)

# ── In-memory progress tracking ──────────────────────────────────────

_ANALYZE_JOBS: dict[str, AnalyzeStatus] = {}


def get_analyze_status(repo_root: Path) -> AnalyzeStatus:
    key = str(repo_root.resolve())
    return _ANALYZE_JOBS.get(key, AnalyzeStatus())


def _set_status(key: str, **kwargs) -> AnalyzeStatus:
    if key not in _ANALYZE_JOBS:
        _ANALYZE_JOBS[key] = AnalyzeStatus()
    status = _ANALYZE_JOBS[key]
    for k, v in kwargs.items():
        setattr(status, k, v)
    return status


# ── Pipeline ─────────────────────────────────────────────────────────

async def analyze_repo(repo_root: Path, settings: WorkspaceSettings,
                       depth: str = "standard") -> AnalyzeStatus:
    """Run the full understanding pipeline.

    depth:
        'quick'    - files only (no directory/project summaries)
        'standard' - files + directories + project (local model)
        'deep'     - everything + patterns + cloud escalation
    """
    key = str(repo_root.resolve())
    _set_status(key, state="scanning", phase="Discovering files...",
                error="", files_done=0, directories_done=0)

    try:
        # 1. Discover files
        files = discover_files(repo_root)
        _set_status(key, files_total=len(files),
                    phase=f"Found {len(files)} files")

        if not files:
            return _set_status(key, state="done", phase="No files found")

        # 2. Parse all files with AST parser
        _set_status(key, state="parsing", phase="AST parsing files...")
        structures = parse_repo(repo_root, files)
        logger.info("Parsed %d files", len(structures))

        # 3. Build dependency graph
        _set_status(key, phase="Building dependency graph...")
        graph = DependencyGraph()
        graph.build_from_structures(repo_root, structures)
        graph.save(repo_root)
        logger.info("Built graph: %d nodes", len(graph._nodes))

        # 4. Load or create knowledge base
        kb = KnowledgeBase.load(repo_root)

        # 5. Summarize files
        _set_status(key, state="summarizing_files",
                    phase="Summarizing files with local LLM...")
        provider = build_local_provider(settings)
        sem = asyncio.Semaphore(settings.max_concurrent_summaries)

        async def _summarize_one(rel_path: str, fs: FileStructure) -> None:
            async with sem:
                parent_ctx = kb.get_context_for_path(rel_path)
                result = await summarize_file(provider, fs, parent_ctx)
                kb.set_file_summary(
                    path=rel_path,
                    summary=result.get("summary", ""),
                    language=fs.language,
                    functions=[s.name for s in fs.symbols if s.symbol_type in ("function", "method")],
                    classes=[s.name for s in fs.symbols if s.symbol_type == "class"],
                    imports=[i.source for i in fs.imports],
                    line_count=fs.line_count,
                )
                kb.record_mtime(repo_root, rel_path)
                status = _ANALYZE_JOBS[key]
                status.files_done += 1
                status.phase = f"Summarized {status.files_done}/{status.files_total} files"

        tasks = [_summarize_one(rel, fs) for rel, fs in structures.items()]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("File summaries: %d", len(kb.file_summaries))

        if depth == "quick":
            kb.last_analyzed = datetime.now(timezone.utc).isoformat()
            kb.save(repo_root)
            return _set_status(key, state="done", phase="Quick analysis complete")

        # 6. Summarize directories (bottom-up)
        _set_status(key, state="summarizing_dirs", phase="Summarizing directories...")
        dir_files: dict[str, list[str]] = defaultdict(list)
        for rel in structures:
            parent = str(Path(rel).parent)
            dir_files[parent].append(rel)

        # Sort by depth (deepest first for bottom-up)
        sorted_dirs = sorted(dir_files.keys(), key=lambda d: d.count("/") + d.count("\\"), reverse=True)
        _set_status(key, directories_total=len(sorted_dirs))

        for dir_path in sorted_dirs:
            file_sums = [kb.file_summaries[f] for f in dir_files[dir_path]
                         if f in kb.file_summaries]
            # Get subdirectory summaries
            sub_sums = []
            for d in sorted_dirs:
                if d != dir_path and d.startswith(dir_path + "/") and d.count("/") == dir_path.count("/") + 1:
                    ds = kb.get_directory_summary(d)
                    if ds:
                        sub_sums.append(ds)

            result = await summarize_directory(provider, dir_path, file_sums, sub_sums)
            kb.set_directory_summary(
                path=dir_path,
                summary=result.get("summary", ""),
                purpose=result.get("purpose", ""),
                files=dir_files[dir_path],
                subdirectories=[d for d in sorted_dirs
                                if d.startswith(dir_path + "/") and d.count("/") == dir_path.count("/") + 1],
            )
            status = _ANALYZE_JOBS[key]
            status.directories_done += 1
            status.phase = f"Summarized {status.directories_done}/{status.directories_total} directories"

        logger.info("Directory summaries: %d", len(kb.directory_summaries))

        # 7. Project overview
        _set_status(key, state="summarizing_project", phase="Generating project overview...")
        proj_provider = provider
        if depth == "deep" and settings.use_cloud_for_project_summary:
            try:
                proj_provider = build_frontier_provider(
                    settings.default_escalation_provider, settings)
            except Exception:
                proj_provider = provider  # fallback to local

        graph_stats = {
            "total_files": len(structures),
            "total_symbols": sum(len(fs.symbols) for fs in structures.values()),
            "total_imports": sum(len(fs.imports) for fs in structures.values()),
            "languages": list(set(fs.language for fs in structures.values() if fs.language != "unknown")),
        }

        proj_result = await summarize_project(
            proj_provider,
            list(kb.directory_summaries.values()),
            graph_stats,
            kb.patterns,
        )
        kb.set_project_overview(
            name=proj_result.get("name", repo_root.name),
            summary=proj_result.get("summary", ""),
            architecture=proj_result.get("architecture", ""),
            tech_stack=proj_result.get("tech_stack", []),
            components=proj_result.get("components", []),
            patterns=proj_result.get("patterns", []),
            entry_points=proj_result.get("entry_points", []),
        )

        # 8. Pattern extraction (deep only)
        if depth == "deep":
            _set_status(key, state="extracting_patterns", phase="Extracting patterns...")
            try:
                patterns = await extract_patterns(proj_provider, kb, structures, graph)
                kb.patterns = patterns
            except Exception as exc:
                logger.warning("Pattern extraction failed: %s", exc)

        # 9. Save
        kb.last_analyzed = datetime.now(timezone.utc).isoformat()
        kb.save(repo_root)

        phase_text = "Deep analysis complete" if depth == "deep" else "Analysis complete"
        return _set_status(key, state="done", phase=phase_text)

    except Exception as exc:
        logger.exception("Analysis failed")
        return _set_status(key, state="error", error=str(exc),
                           phase=f"Error: {exc}")
