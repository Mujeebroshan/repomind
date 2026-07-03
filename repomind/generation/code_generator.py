"""Context-rich code generation using repository understanding."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from ..understanding.knowledge_base import KnowledgeBase
from ..providers.base import Provider, complete


_SYSTEM = """You are an expert code generator. Given a description, codebase context,
and conventions, generate production-quality code that matches the project's style.
Respond with valid JSON (no markdown fences):
{"file_path":"suggested/path.py","content":"...the full code...",
"explanation":"why this approach","related_files":["files to review"]}"""


async def generate_code(repo_root: Path, provider: Provider,
                        description: str, target_path: str = "",
                        knowledge_base: Optional[KnowledgeBase] = None,
                        structures=None) -> dict:
    """Generate code informed by repository understanding."""
    # Load KB if needed
    kb = knowledge_base or KnowledgeBase.load(repo_root)

    # Build rich context
    parts = [f"Generate code for: {description}"]
    if target_path:
        parts.append(f"Target file: {target_path}")

    # Project context
    overview = kb.get_project_overview()
    if overview:
        parts.append(f"Project: {overview.get('summary', '')[:300]}")
        if overview.get("tech_stack"):
            parts.append(f"Tech stack: {', '.join(overview['tech_stack'])}")
        if overview.get("patterns"):
            parts.append(f"Patterns: {', '.join(overview['patterns'][:5])}")

    # Find relevant patterns
    if kb.patterns:
        relevant_patterns = [p for p in kb.patterns
                             if any(kw in description.lower()
                                    for kw in p.get("name", "").lower().split())][:3]
        if relevant_patterns:
            parts.append("Relevant patterns:")
            for p in relevant_patterns:
                parts.append(f"  - {p.get('name', '')}: {p.get('description', '')[:100]}")

    # Similar files context
    similar = kb.search_summaries(description)[:3]
    if similar:
        parts.append("Similar existing code:")
        for s in similar:
            parts.append(f"  - {s.get('path', '')}: {s.get('summary', '')[:100]}")

    messages = [{"role": "user", "content": "\n\n".join(parts)}]
    try:
        reply = await complete(provider, messages, system=_SYSTEM, temperature=0.3)
        text = reply.strip()
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
            return {"file_path": target_path or "generated.py",
                    "content": reply, "explanation": "Raw LLM output",
                    "related_files": []}
    except Exception as exc:
        return {"file_path": target_path or "error.py",
                "content": f"# Error: {exc}",
                "explanation": str(exc), "related_files": []}
