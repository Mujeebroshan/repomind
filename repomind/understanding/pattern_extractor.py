"""Code pattern and convention extractor.

Analyzes the knowledge base and AST data to identify design patterns,
naming conventions, error handling approaches, and architectural decisions.
"""
from __future__ import annotations

import json
import re

from ..providers.base import Provider, complete
from .knowledge_base import KnowledgeBase
from ..parser.ast_parser import FileStructure
from ..graph.builder import DependencyGraph
from ..graph.query import get_most_important_files


_SYSTEM = """You are an expert software architect. Analyze the codebase information
and identify patterns, conventions, and architectural decisions.
Respond ONLY with valid JSON (no markdown fences). Format:
[{"name":"pattern name","description":"what it does","category":"design_pattern|naming|error_handling|architecture|testing",
"files_using":["file1.py","file2.py"]}]"""


async def extract_patterns(provider: Provider, knowledge_base: KnowledgeBase,
                           structures: dict[str, FileStructure],
                           graph: DependencyGraph) -> list[dict]:
    """Use LLM to identify patterns from the accumulated understanding."""
    # Gather data for the prompt
    overview = knowledge_base.get_project_overview()
    top_files = get_most_important_files(graph, top_n=10)

    # Collect naming patterns from symbols
    func_names: list[str] = []
    class_names: list[str] = []
    for fs in structures.values():
        for sym in fs.symbols:
            if sym.symbol_type == "function":
                func_names.append(sym.name)
            elif sym.symbol_type == "class":
                class_names.append(sym.name)

    # Build prompt
    parts = ["Codebase analysis for pattern detection:"]
    if overview:
        parts.append(f"Project: {overview.get('summary', '')[:300]}")
        parts.append(f"Tech stack: {overview.get('tech_stack', [])}")

    parts.append(f"\nMost important files (by PageRank):")
    for fp, score in top_files:
        fs_summary = knowledge_base.get_file_summary(fp)
        summary_text = fs_summary.get("summary", "")[:100] if fs_summary else ""
        parts.append(f"  {fp} (score={score:.4f}): {summary_text}")

    if func_names:
        parts.append(f"\nSample function names: {', '.join(func_names[:30])}")
    if class_names:
        parts.append(f"Sample class names: {', '.join(class_names[:20])}")

    # File structure patterns
    file_exts: dict[str, int] = {}
    for rel in structures:
        ext = rel.rsplit(".", 1)[-1] if "." in rel else ""
        file_exts[ext] = file_exts.get(ext, 0) + 1
    parts.append(f"\nFile types: {json.dumps(file_exts)}")

    # Directory structure
    dirs = list(knowledge_base.directory_summaries.keys())[:15]
    if dirs:
        parts.append(f"Directories: {', '.join(dirs)}")

    messages = [{"role": "user", "content": "\n".join(parts)}]
    try:
        reply = await complete(provider, messages, system=_SYSTEM, temperature=0.3)
        # Parse response
        text = reply.strip()
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
        return [{"name": "unknown", "description": reply[:300],
                 "category": "architecture", "files_using": []}]
    except Exception as exc:
        return [{"name": "error", "description": str(exc),
                 "category": "error", "files_using": []}]
