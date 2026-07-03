"""Proactive code improvement suggestions."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from ..understanding.knowledge_base import KnowledgeBase
from ..providers.base import Provider, complete


_SYSTEM = """You are a code reviewer. Analyze the codebase summaries and patterns
to suggest improvements. Respond ONLY with valid JSON array (no markdown fences):
[{"file_path":"path/to/file.py","line_start":0,"line_end":0,
"category":"naming|error_handling|pattern|dead_code|missing_test|performance",
"message":"description of issue","suggested_code":"improved code or empty"}]"""


async def generate_suggestions(repo_root: Path, provider: Provider,
                               knowledge_base: Optional[KnowledgeBase] = None,
                               structures=None,
                               max_suggestions: int = 10) -> list[dict]:
    """Analyze the codebase and suggest improvements."""
    kb = knowledge_base or KnowledgeBase.load(repo_root)

    # Build context
    parts = ["Analyze this codebase for improvement suggestions:"]

    overview = kb.get_project_overview()
    if overview:
        parts.append(f"Project: {overview.get('summary', '')[:200]}")
        if overview.get("patterns"):
            parts.append(f"Current patterns: {', '.join(overview['patterns'][:5])}")

    # Sample file summaries
    file_items = list(kb.file_summaries.items())[:20]
    if file_items:
        parts.append("\nFile summaries:")
        for fp, fs in file_items:
            funcs = fs.get("functions", [])[:5]
            parts.append(f"  {fp} ({fs.get('language','')}): {fs.get('summary', '')[:80]}")
            if funcs:
                parts.append(f"    functions: {', '.join(funcs)}")

    parts.append(f"\nProvide up to {max_suggestions} concrete, actionable suggestions.")

    messages = [{"role": "user", "content": "\n".join(parts)}]
    try:
        reply = await complete(provider, messages, system=_SYSTEM, temperature=0.3)
        text = reply.strip()
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result[:max_suggestions]
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())[:max_suggestions]
                except json.JSONDecodeError:
                    pass
        return [{"file_path": "", "message": reply[:300], "category": "general",
                 "suggested_code": ""}]
    except Exception as exc:
        return [{"file_path": "", "message": f"Suggestion generation failed: {exc}",
                 "category": "error", "suggested_code": ""}]
