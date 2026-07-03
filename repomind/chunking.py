from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_DIRS = {
    ".git", ".repomind", "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", ".next", ".cache", "target", "vendor", ".idea", ".vscode",
    "coverage", ".pytest_cache", ".mypy_cache", "egg-info",
}

# Extensions we treat as "source-like" and worth indexing. Anything else
# (images, binaries, lockfiles, etc.) is skipped.
INCLUDED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".rb",
    ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".swift", ".m", ".scala",
    ".sql", ".sh", ".md", ".rst", ".yaml", ".yml", ".toml", ".json",
    ".html", ".css", ".scss", ".vue", ".svelte", ".graphql", ".proto",
}

MAX_FILE_SIZE_BYTES = 1_000_000  # skip anything bigger than ~1MB; almost never source code
CHUNK_LINES = 60
CHUNK_OVERLAP_LINES = 10


@dataclass
class Chunk:
    file_path: str  # relative to repo root
    start_line: int  # 1-indexed, inclusive
    end_line: int  # 1-indexed, inclusive
    text: str


def discover_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() not in INCLUDED_EXTENSIONS:
                continue
            try:
                if p.stat().st_size > MAX_FILE_SIZE_BYTES or p.stat().st_size == 0:
                    continue
            except OSError:
                continue
            files.append(p)
    return files


def read_text_safely(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def chunk_file(repo_root: Path, file_path: Path) -> list[Chunk]:
    content = read_text_safely(file_path)
    if content is None:
        return []
    lines = content.splitlines()
    if not lines:
        return []

    rel_path = str(file_path.relative_to(repo_root))
    chunks: list[Chunk] = []
    step = max(CHUNK_LINES - CHUNK_OVERLAP_LINES, 1)
    i = 0
    while i < len(lines):
        window = lines[i : i + CHUNK_LINES]
        if not window:
            break
        text = "\n".join(window).strip()
        if text:
            chunks.append(
                Chunk(
                    file_path=rel_path,
                    start_line=i + 1,
                    end_line=min(i + len(window), len(lines)),
                    text=text,
                )
            )
        if i + CHUNK_LINES >= len(lines):
            break
        i += step
    return chunks


def chunk_repo(repo_root: Path) -> tuple[list[Path], list[Chunk]]:
    files = discover_files(repo_root)
    all_chunks: list[Chunk] = []
    for f in files:
        all_chunks.extend(chunk_file(repo_root, f))
    return files, all_chunks
