"""Hierarchical LLM-powered summarization engine.

Bottom-up: files first, then directories (with file context),
then the full project.  Uses Ollama locally for all summaries.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..providers.base import Provider, complete
from ..parser.ast_parser import FileStructure


# ── Prompt helpers ────────────────────────────────────────────────────

_FILE_SYSTEM = """You are a code analyst. Given a source file, produce a JSON summary.
Respond ONLY with valid JSON (no markdown fences). Keys:
{"summary":"1-3 sentence purpose","purpose":"what role this file plays",
"key_functions":["fn1","fn2"],"key_classes":["cls1"],
"role_in_system":"how it fits the larger project"}"""

_DIR_SYSTEM = """You are a software architect. Given summaries of files in a directory,
produce a JSON summary. Respond ONLY with valid JSON. Keys:
{"summary":"purpose of this directory","purpose":"architectural role",
"key_files":["most important files"],"interactions":"how files work together"}"""

_PROJ_SYSTEM = """You are a senior architect. Given directory summaries and stats,
produce a JSON project overview. Respond ONLY with valid JSON. Keys:
{"name":"project name","summary":"1-paragraph overview",
"architecture":"architectural style","tech_stack":["tech1","tech2"],
"components":["component1"],"patterns":["pattern1"],
"entry_points":["main entry files"]}"""


def _extract_json(text: str) -> dict:
    """Best-effort extraction of JSON from LLM response."""
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find first { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {"summary": text[:500]}


def _truncate(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + f"\n\n... ({len(text) - max_chars} chars truncated) ...\n\n" + text[-half:]


# ── Public API ────────────────────────────────────────────────────────

async def summarize_file(provider: Provider, fs: FileStructure,
                         parent_dir_context: str = "") -> dict:
    """Generate a summary for a single file using the LLM."""
    symbols = [f"  {s.symbol_type}: {s.name}" for s in fs.symbols[:30]]
    imports = [f"  {i.source}" for i in fs.imports[:20]]

    prompt_parts = [f"File: {fs.file_path}  (language: {fs.language}, {fs.line_count} lines)"]
    if parent_dir_context:
        prompt_parts.append(f"Parent directory context:\n{parent_dir_context}")
    if symbols:
        prompt_parts.append("Symbols:\n" + "\n".join(symbols))
    if imports:
        prompt_parts.append("Imports:\n" + "\n".join(imports))
    prompt_parts.append(f"Source:\n{_truncate(fs.raw_text)}")

    messages = [{"role": "user", "content": "\n\n".join(prompt_parts)}]
    try:
        reply = await complete(provider, messages, system=_FILE_SYSTEM, temperature=0.2)
        result = _extract_json(reply)
        # Ensure minimum fields
        result.setdefault("summary", "")
        result.setdefault("purpose", "")
        result.setdefault("key_functions", [s.name for s in fs.symbols if s.symbol_type == "function"][:10])
        result.setdefault("key_classes", [s.name for s in fs.symbols if s.symbol_type == "class"][:10])
        return result
    except Exception as exc:
        return {
            "summary": f"Auto-summary failed ({exc}); file has {fs.line_count} lines, "
                       f"{len(fs.symbols)} symbols, {len(fs.imports)} imports.",
            "purpose": "", "key_functions": [], "key_classes": [],
        }


async def summarize_directory(provider: Provider, dir_path: str,
                              file_summaries: list[dict],
                              subdirectory_summaries: list[dict]) -> dict:
    """Generate a directory summary from its file summaries."""
    parts = [f"Directory: {dir_path}", f"Contains {len(file_summaries)} files."]
    for fs in file_summaries[:15]:
        parts.append(f"  {fs.get('path','?')}: {fs.get('summary','')[:150]}")
    if subdirectory_summaries:
        parts.append("Subdirectories:")
        for ds in subdirectory_summaries[:8]:
            parts.append(f"  {ds.get('path','?')}: {ds.get('summary','')[:100]}")
    messages = [{"role": "user", "content": "\n".join(parts)}]
    try:
        reply = await complete(provider, messages, system=_DIR_SYSTEM, temperature=0.2)
        result = _extract_json(reply)
        result.setdefault("summary", "")
        result.setdefault("purpose", "")
        return result
    except Exception as exc:
        return {"summary": f"Directory with {len(file_summaries)} files ({exc})",
                "purpose": ""}


async def summarize_project(provider: Provider, directory_summaries: list[dict],
                            graph_stats: dict, patterns: list[dict]) -> dict:
    """Generate the project-level overview."""
    parts = ["Project analysis:", f"Stats: {json.dumps(graph_stats)}"]
    for ds in directory_summaries[:20]:
        parts.append(f"  {ds.get('path','?')}: {ds.get('summary','')[:120]}")
    if patterns:
        parts.append("Patterns detected: " + ", ".join(p.get("name", "") for p in patterns[:10]))
    messages = [{"role": "user", "content": "\n".join(parts)}]
    try:
        reply = await complete(provider, messages, system=_PROJ_SYSTEM, temperature=0.3)
        return _extract_json(reply)
    except Exception as exc:
        return {"name": "", "summary": f"Project overview generation failed ({exc})",
                "architecture": "", "tech_stack": [], "components": [],
                "patterns": [], "entry_points": []}
