"""Aider-style compact repository map.

Generates a token-efficient structural summary showing file tree with
key symbols, ranked by PageRank importance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from collections import defaultdict

from ..understanding.knowledge_base import KnowledgeBase
from ..graph.builder import DependencyGraph
from ..graph.query import get_most_important_files


def generate_repo_map(repo_root: Path, structures=None, graph=None,
                      max_tokens: int = 1500) -> str:
    """Generate a compact repo map.  ~4 chars per token budget."""
    max_chars = max_tokens * 4

    # Try to load graph for ranking
    if graph is None:
        try:
            graph = DependencyGraph.load(repo_root)
        except Exception:
            graph = None

    # Get file list (ranked if graph available)
    ranked_files: list[str] = []
    if graph and graph._nodes:
        ranked_files = [fp for fp, _ in get_most_important_files(graph, top_n=100)]
    else:
        # Walk filesystem
        for p in sorted(repo_root.rglob("*")):
            if p.is_file() and not _is_ignored(p, repo_root):
                ranked_files.append(str(p.relative_to(repo_root)))

    if not ranked_files:
        return "(empty repository)"

    # Load KB for symbol info
    kb: Optional[KnowledgeBase] = None
    try:
        kb = KnowledgeBase.load(repo_root)
    except Exception:
        pass

    # Group by directory
    dir_files: dict[str, list[str]] = defaultdict(list)
    for fp in ranked_files:
        parent = str(Path(fp).parent) if Path(fp).parent != Path(".") else "."
        dir_files[parent].append(fp)

    # Build tree
    lines: list[str] = []
    used = 0
    sorted_dirs = sorted(dir_files.keys())

    for d in sorted_dirs:
        dir_line = f"📁 {d}/" if d != "." else "📁 ./"
        lines.append(dir_line)
        used += len(dir_line)
        if used > max_chars:
            lines.append("  ...")
            break

        for fp in dir_files[d]:
            fname = Path(fp).name
            # Get symbols from KB
            symbols_str = ""
            if kb:
                fs = kb.get_file_summary(fp)
                if fs:
                    syms = fs.get("functions", [])[:4] + fs.get("classes", [])[:2]
                    if syms:
                        symbols_str = f"  → {', '.join(syms)}"
            file_line = f"  ├── {fname}{symbols_str}"
            if used + len(file_line) > max_chars:
                lines.append("  └── ...")
                return "\n".join(lines)
            lines.append(file_line)
            used += len(file_line)

    return "\n".join(lines)


def _is_ignored(path: Path, root: Path) -> bool:
    """Skip common non-source directories."""
    parts = path.relative_to(root).parts
    skip = {".git", ".repomind", "__pycache__", "node_modules", ".venv",
            "venv", ".mypy_cache", ".pytest_cache", "dist", "build", ".egg-info"}
    return any(p in skip or p.startswith(".") and p != "." for p in parts)
