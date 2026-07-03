"""Language registry for Tree-sitter grammar management.

Maps file extensions to language names and lazily loads Tree-sitter
grammar objects.  Languages without an installed grammar gracefully
fall back to None, which signals the chunker to use line-window mode.
"""
from __future__ import annotations

import importlib
from typing import Optional

from tree_sitter import Language, Parser

# Extension → (language_name, tree_sitter_package_name)
LANGUAGE_MAP: dict[str, tuple[str, str]] = {
    ".py":   ("python",     "tree_sitter_python"),
    ".js":   ("javascript", "tree_sitter_javascript"),
    ".jsx":  ("javascript", "tree_sitter_javascript"),
    ".ts":   ("typescript", "tree_sitter_typescript"),
    ".tsx":  ("typescript", "tree_sitter_typescript"),
    ".go":   ("go",         "tree_sitter_go"),
    ".rs":   ("rust",       "tree_sitter_rust"),
    ".java": ("java",       "tree_sitter_java"),
    ".c":    ("c",          "tree_sitter_c"),
    ".h":    ("c",          "tree_sitter_c"),
    ".cpp":  ("cpp",        "tree_sitter_cpp"),
    ".hpp":  ("cpp",        "tree_sitter_cpp"),
    ".cc":   ("cpp",        "tree_sitter_cpp"),
}

_parser_cache: dict[str, Parser] = {}
_failed_languages: set[str] = set()


def get_parser(extension: str) -> Optional[Parser]:
    """Get a Tree-sitter parser for *extension*.  Returns ``None`` when
    the grammar package is not installed.  Results are cached."""
    if extension not in LANGUAGE_MAP:
        return None
    lang_name, pkg_name = LANGUAGE_MAP[extension]
    if lang_name in _failed_languages:
        return None
    if lang_name in _parser_cache:
        return _parser_cache[lang_name]
    try:
        mod = importlib.import_module(pkg_name)
        lang_fn = getattr(mod, "language", None)
        if lang_fn is None:
            for suffix in (lang_name, "tsx" if extension == ".tsx" else lang_name):
                lang_fn = getattr(mod, f"language_{suffix}", None)
                if lang_fn is not None:
                    break
        if lang_fn is None:
            _failed_languages.add(lang_name)
            return None
        language = Language(lang_fn())
        parser = Parser(language)
        _parser_cache[lang_name] = parser
        return parser
    except (ImportError, OSError, Exception):
        _failed_languages.add(lang_name)
        return None


def get_language_name(extension: str) -> str:
    """Return the language name for *extension*, or ``'unknown'``."""
    if extension in LANGUAGE_MAP:
        return LANGUAGE_MAP[extension][0]
    return "unknown"


def supported_extensions() -> set[str]:
    """All file extensions with a Tree-sitter grammar mapping."""
    return set(LANGUAGE_MAP.keys())
