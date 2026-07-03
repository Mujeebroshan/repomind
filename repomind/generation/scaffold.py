"""Project scaffold extraction from learned repository patterns."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from collections import defaultdict

from ..understanding.knowledge_base import KnowledgeBase


def extract_scaffold(repo_root: Path,
                     knowledge_base: Optional[KnowledgeBase] = None,
                     structures=None) -> dict:
    """Extract a reusable scaffold from the analysed repository.

    Returns a dict with:
    - directories: list of directory paths
    - files: list of {path, purpose, is_config, is_entry}
    - naming_patterns: observed naming conventions
    - tech_stack: detected technologies
    """
    kb = knowledge_base or KnowledgeBase.load(repo_root)

    dirs = sorted(kb.directory_summaries.keys())
    files_info: list[dict] = []
    naming: dict[str, list[str]] = defaultdict(list)

    for fp, fs in kb.file_summaries.items():
        name = Path(fp).name
        is_config = name in ("pyproject.toml", "package.json", "Cargo.toml",
                             "go.mod", ".env", ".env.example", "Makefile",
                             "Dockerfile", "docker-compose.yml") or name.endswith(".toml")
        is_entry = any(kw in name.lower() for kw in ("main", "cli", "app", "__main__", "index"))
        files_info.append({
            "path": fp,
            "purpose": fs.get("summary", "")[:100],
            "is_config": is_config,
            "is_entry": is_entry,
            "language": fs.get("language", ""),
        })
        # Naming patterns
        if name.startswith("test_") or name.endswith("_test.py"):
            naming["test_files"].append(fp)
        if "_provider" in name:
            naming["provider_pattern"].append(fp)
        if name == "__init__.py":
            naming["packages"].append(fp)

    overview = kb.get_project_overview()
    return {
        "directories": dirs,
        "files": files_info,
        "naming_patterns": dict(naming),
        "tech_stack": overview.get("tech_stack", []) if overview else [],
        "patterns": overview.get("patterns", []) if overview else [],
        "entry_points": overview.get("entry_points", []) if overview else [],
    }


def generate_scaffold_plan(scaffold: dict, modifications: str = "") -> str:
    """Human-readable scaffold plan."""
    lines = ["# Project Scaffold Plan\n"]
    lines.append("## Directory Structure")
    for d in scaffold.get("directories", []):
        lines.append(f"  📁 {d}/")

    lines.append("\n## Key Files")
    for f in scaffold.get("files", []):
        marker = "⚙️" if f.get("is_config") else "🚀" if f.get("is_entry") else "📄"
        lines.append(f"  {marker} {f['path']} — {f.get('purpose', '')}")

    if scaffold.get("tech_stack"):
        lines.append(f"\n## Tech Stack: {', '.join(scaffold['tech_stack'])}")

    if scaffold.get("patterns"):
        lines.append(f"\n## Patterns: {', '.join(scaffold['patterns'])}")

    if modifications:
        lines.append(f"\n## Modifications: {modifications}")

    return "\n".join(lines)
