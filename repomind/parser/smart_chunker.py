"""AST-boundary-aware code chunking.

Chunks code at natural semantic boundaries (functions, classes, methods)
rather than arbitrary line windows.  Falls back to line-window chunking
for files without Tree-sitter support.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .ast_parser import FileStructure, CodeSymbol

MAX_CHUNK_LINES = 120
FALLBACK_CHUNK_LINES = 60
FALLBACK_OVERLAP = 10


@dataclass
class SmartChunk:
    """A semantically meaningful piece of source code."""
    file_path: str
    language: str
    start_line: int
    end_line: int
    text: str
    chunk_type: str        # header | function | class | method | block
    symbol_name: str = ""
    parent_symbol: str = ""
    metadata: dict = field(default_factory=dict)


# ── Symbol-based chunking ─────────────────────────────────────────────

def _header_chunk(fs: FileStructure) -> SmartChunk | None:
    """Extract the file header (imports + module docstring) as its own chunk."""
    if not fs.raw_text:
        return None
    lines = fs.raw_text.splitlines()
    # Header = everything before the first symbol
    first_sym_line = min((s.start_line for s in fs.symbols), default=len(lines) + 1)
    header_end = max(first_sym_line - 1, 0)
    if header_end <= 0:
        return None
    text = "\n".join(lines[:header_end]).strip()
    if not text:
        return None
    return SmartChunk(
        file_path=fs.file_path, language=fs.language,
        start_line=1, end_line=header_end,
        text=text, chunk_type="header",
    )


def _split_large_symbol(sym: CodeSymbol, file_path: str, language: str,
                         full_lines: list[str]) -> list[SmartChunk]:
    """Split a symbol larger than MAX_CHUNK_LINES into sub-chunks."""
    start = sym.start_line - 1  # 0-indexed
    end = sym.end_line           # exclusive
    step = max(FALLBACK_CHUNK_LINES - FALLBACK_OVERLAP, 1)
    chunks: list[SmartChunk] = []
    i = start
    part = 0
    while i < end:
        window = full_lines[i:i + FALLBACK_CHUNK_LINES]
        if not window:
            break
        text = "\n".join(window).strip()
        if text:
            part += 1
            chunks.append(SmartChunk(
                file_path=file_path, language=language,
                start_line=i + 1, end_line=min(i + len(window), end),
                text=text, chunk_type="block",
                symbol_name=f"{sym.name}_part{part}",
                parent_symbol=sym.parent,
                metadata={"original_symbol": sym.name, "symbol_type": sym.symbol_type},
            ))
        if i + FALLBACK_CHUNK_LINES >= end:
            break
        i += step
    return chunks


def _chunk_by_symbols(fs: FileStructure) -> list[SmartChunk]:
    """Create chunks aligned to AST symbol boundaries."""
    chunks: list[SmartChunk] = []
    lines = fs.raw_text.splitlines()

    # 1. File header
    hdr = _header_chunk(fs)
    if hdr:
        chunks.append(hdr)

    # 2. Separate top-level symbols from methods
    top_level = [s for s in fs.symbols if not s.parent]
    methods = [s for s in fs.symbols if s.parent]

    for sym in top_level:
        line_count = sym.end_line - sym.start_line + 1

        if sym.symbol_type == "class":
            # Class header chunk: first few lines (signature + docstring)
            header_lines = min(10, line_count)
            cls_text = "\n".join(lines[sym.start_line - 1:sym.start_line - 1 + header_lines]).strip()
            if cls_text:
                chunks.append(SmartChunk(
                    file_path=fs.file_path, language=fs.language,
                    start_line=sym.start_line, end_line=sym.start_line + header_lines - 1,
                    text=cls_text, chunk_type="class",
                    symbol_name=sym.name,
                ))
            # Individual method chunks
            cls_methods = [m for m in methods if m.parent == sym.name]
            for m in cls_methods:
                m_lines = m.end_line - m.start_line + 1
                if m_lines > MAX_CHUNK_LINES:
                    chunks.extend(_split_large_symbol(m, fs.file_path, fs.language, lines))
                else:
                    chunks.append(SmartChunk(
                        file_path=fs.file_path, language=fs.language,
                        start_line=m.start_line, end_line=m.end_line,
                        text=m.body_text or "\n".join(lines[m.start_line-1:m.end_line]).strip(),
                        chunk_type="method",
                        symbol_name=m.name, parent_symbol=m.parent,
                    ))
        else:
            # Function / constant
            if line_count > MAX_CHUNK_LINES:
                chunks.extend(_split_large_symbol(sym, fs.file_path, fs.language, lines))
            else:
                chunks.append(SmartChunk(
                    file_path=fs.file_path, language=fs.language,
                    start_line=sym.start_line, end_line=sym.end_line,
                    text=sym.body_text or "\n".join(lines[sym.start_line-1:sym.end_line]).strip(),
                    chunk_type="function",
                    symbol_name=sym.name,
                ))

    return chunks


# ── Line-window fallback ──────────────────────────────────────────────

def _chunk_by_lines(file_path: str, text: str, language: str) -> list[SmartChunk]:
    """Overlapping line-window chunking for files without AST support."""
    lines = text.splitlines()
    if not lines:
        return []
    chunks: list[SmartChunk] = []
    step = max(FALLBACK_CHUNK_LINES - FALLBACK_OVERLAP, 1)
    i = 0
    while i < len(lines):
        window = lines[i:i + FALLBACK_CHUNK_LINES]
        if not window:
            break
        block = "\n".join(window).strip()
        if block:
            chunks.append(SmartChunk(
                file_path=file_path, language=language,
                start_line=i + 1, end_line=min(i + len(window), len(lines)),
                text=block, chunk_type="block",
            ))
        if i + FALLBACK_CHUNK_LINES >= len(lines):
            break
        i += step
    return chunks


# ── Public API ────────────────────────────────────────────────────────

def smart_chunk_file(repo_root: Path, file_path: Path,
                     file_structure: FileStructure) -> list[SmartChunk]:
    """Chunk a file using AST boundaries when available, else line windows."""
    if file_structure.has_ast and file_structure.symbols:
        chunks = _chunk_by_symbols(file_structure)
        if chunks:
            return chunks
    # Fallback
    if file_structure.raw_text:
        return _chunk_by_lines(file_structure.file_path, file_structure.raw_text,
                               file_structure.language)
    return []


def smart_chunk_repo(repo_root: Path,
                     file_structures: dict[str, FileStructure],
                     ) -> tuple[list[Path], list[SmartChunk]]:
    """Chunk all parsed files.  Returns (file_list, all_chunks)."""
    all_chunks: list[SmartChunk] = []
    files: list[Path] = []
    for rel_path, fs in file_structures.items():
        fp = repo_root / rel_path
        files.append(fp)
        all_chunks.extend(smart_chunk_file(repo_root, fp, fs))
    return files, all_chunks
