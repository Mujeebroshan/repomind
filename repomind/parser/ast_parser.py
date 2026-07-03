"""Tree-sitter AST parsing engine.

Parses source files into structured representations: extracts functions,
classes, methods, imports, exports, and their relationships.  This replaces
the naive line-counting approach with semantic code understanding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .languages import get_parser, get_language_name


# ── Data classes ──────────────────────────────────────────────────────

@dataclass
class CodeSymbol:
    """A named code element extracted from AST."""
    name: str
    symbol_type: str   # function | class | method | constant
    start_line: int    # 1-indexed
    end_line: int      # 1-indexed
    docstring: str = ""
    parent: str = ""   # parent class name for methods
    body_text: str = ""


@dataclass
class ImportInfo:
    """A single import statement."""
    source: str
    names: list[str] = field(default_factory=list)
    alias: str = ""
    line: int = 0


@dataclass
class FileStructure:
    """Complete structural analysis of a single source file."""
    file_path: str          # relative to repo root
    language: str
    symbols: list[CodeSymbol] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    line_count: int = 0
    has_ast: bool = False
    raw_text: str = ""


# ── Helpers ───────────────────────────────────────────────────────────

def _read_file_safely(path: Path) -> Optional[str]:
    """Read file text, returning None on any error."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _node_text(node) -> str:
    return node.text.decode("utf-8", errors="replace") if node else ""


# ── Python extraction ─────────────────────────────────────────────────

def _py_docstring(node) -> str:
    """Extract docstring from the first statement in a block."""
    for child in node.children:
        if child.type == "block":
            for stmt in child.children:
                if stmt.type == "expression_statement":
                    for sub in stmt.children:
                        if sub.type == "string":
                            t = _node_text(sub)
                            for q in ('"""', "'''"):
                                if t.startswith(q) and t.endswith(q):
                                    return t[3:-3].strip()
                            return t.strip("\"'")
                    return ""
                if stmt.type not in ("comment", "newline"):
                    return ""
    return ""


def _extract_python_symbols(root, src: bytes) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []

    def _walk(node, parent_class=""):
        if node.type == "function_definition":
            n = node.child_by_field_name("name")
            symbols.append(CodeSymbol(
                name=_node_text(n), symbol_type="method" if parent_class else "function",
                start_line=node.start_point[0]+1, end_line=node.end_point[0]+1,
                docstring=_py_docstring(node), parent=parent_class,
                body_text=_node_text(node),
            ))
        elif node.type == "class_definition":
            n = node.child_by_field_name("name")
            name = _node_text(n)
            symbols.append(CodeSymbol(
                name=name, symbol_type="class",
                start_line=node.start_point[0]+1, end_line=node.end_point[0]+1,
                docstring=_py_docstring(node), body_text=_node_text(node),
            ))
            for child in node.children:
                _walk(child, parent_class=name)
            return
        elif node.type == "decorated_definition":
            for child in node.children:
                _walk(child, parent_class=parent_class)
            return
        for child in node.children:
            _walk(child, parent_class=parent_class)

    _walk(root)
    return symbols


def _extract_python_imports(root, src: bytes) -> list[ImportInfo]:
    imports: list[ImportInfo] = []

    def _walk(node):
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append(ImportInfo(source=_node_text(child), line=node.start_point[0]+1))
                elif child.type == "aliased_import":
                    n = child.child_by_field_name("name")
                    a = child.child_by_field_name("alias")
                    if n:
                        imports.append(ImportInfo(
                            source=_node_text(n), alias=_node_text(a) if a else "",
                            line=node.start_point[0]+1,
                        ))
        elif node.type == "import_from_statement":
            mn = node.child_by_field_name("module_name")
            source = _node_text(mn)
            if not source:
                for child in node.children:
                    if child.type == "relative_import":
                        source = _node_text(child)
                        break
            names = []
            for child in node.children:
                if child.type == "dotted_name" and child != mn:
                    names.append(_node_text(child))
                elif child.type == "aliased_import":
                    n = child.child_by_field_name("name")
                    if n:
                        names.append(_node_text(n))
            imports.append(ImportInfo(source=source, names=names, line=node.start_point[0]+1))
        else:
            for child in node.children:
                _walk(child)

    _walk(root)
    return imports


# ── JavaScript / TypeScript extraction ────────────────────────────────

def _extract_js_symbols(root, src: bytes) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []

    def _walk(node, parent_class=""):
        if node.type in ("function_declaration", "generator_function_declaration"):
            n = node.child_by_field_name("name")
            symbols.append(CodeSymbol(
                name=_node_text(n), symbol_type="function",
                start_line=node.start_point[0]+1, end_line=node.end_point[0]+1,
                body_text=_node_text(node),
            ))
        elif node.type == "class_declaration":
            n = node.child_by_field_name("name")
            name = _node_text(n)
            symbols.append(CodeSymbol(
                name=name, symbol_type="class",
                start_line=node.start_point[0]+1, end_line=node.end_point[0]+1,
                body_text=_node_text(node),
            ))
            for child in node.children:
                _walk(child, parent_class=name)
            return
        elif node.type == "method_definition":
            n = node.child_by_field_name("name")
            symbols.append(CodeSymbol(
                name=_node_text(n), symbol_type="method",
                start_line=node.start_point[0]+1, end_line=node.end_point[0]+1,
                parent=parent_class, body_text=_node_text(node),
            ))
        elif node.type in ("lexical_declaration", "variable_declaration"):
            for decl in node.children:
                if decl.type == "variable_declarator":
                    n = decl.child_by_field_name("name")
                    v = decl.child_by_field_name("value")
                    if n and v and v.type in ("arrow_function", "function_expression"):
                        symbols.append(CodeSymbol(
                            name=_node_text(n), symbol_type="function",
                            start_line=node.start_point[0]+1, end_line=node.end_point[0]+1,
                            body_text=_node_text(node),
                        ))
                    elif n and v and v.type == "class":
                        symbols.append(CodeSymbol(
                            name=_node_text(n), symbol_type="class",
                            start_line=node.start_point[0]+1, end_line=node.end_point[0]+1,
                            body_text=_node_text(node),
                        ))
        for child in node.children:
            _walk(child, parent_class=parent_class)

    _walk(root)
    return symbols


def _extract_js_imports(root, src: bytes) -> list[ImportInfo]:
    imports: list[ImportInfo] = []

    def _walk(node):
        if node.type == "import_statement":
            sn = node.child_by_field_name("source")
            source = _node_text(sn).strip("\"'") if sn else ""
            names = []
            for child in node.children:
                if child.type == "import_clause":
                    for sub in child.children:
                        if sub.type == "identifier":
                            names.append(_node_text(sub))
                        elif sub.type == "named_imports":
                            for spec in sub.children:
                                if spec.type == "import_specifier":
                                    nn = spec.child_by_field_name("name")
                                    if nn:
                                        names.append(_node_text(nn))
            imports.append(ImportInfo(source=source, names=names, line=node.start_point[0]+1))
        elif node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn and fn.text == b"require":
                args = node.child_by_field_name("arguments")
                if args:
                    for arg in args.children:
                        if arg.type == "string":
                            imports.append(ImportInfo(
                                source=_node_text(arg).strip("\"'"),
                                line=node.start_point[0]+1,
                            ))
        for child in node.children:
            _walk(child)

    _walk(root)
    return imports


def _extract_js_exports(root, src: bytes) -> list[str]:
    exports: list[str] = []

    def _walk(node):
        if node.type == "export_statement":
            for child in node.children:
                if child.type in ("function_declaration", "class_declaration"):
                    n = child.child_by_field_name("name")
                    if n:
                        exports.append(_node_text(n))
                elif child.type in ("lexical_declaration", "variable_declaration"):
                    for decl in child.children:
                        if decl.type == "variable_declarator":
                            n = decl.child_by_field_name("name")
                            if n:
                                exports.append(_node_text(n))
        for child in node.children:
            _walk(child)

    _walk(root)
    return exports


# ── Generic extraction ────────────────────────────────────────────────

_FUNC_TYPES = {
    "function_definition", "function_declaration", "method_declaration",
    "function_item",  # Rust
}
_CLASS_TYPES = {
    "class_declaration", "class_definition",
    "struct_item", "impl_item", "enum_item",  # Rust
    "type_declaration",                        # Go
    "struct_specifier", "class_specifier",     # C/C++
}


def _extract_generic_symbols(root, src: bytes, lang: str) -> list[CodeSymbol]:
    symbols: list[CodeSymbol] = []

    def _walk(node, parent=""):
        if node.type in _FUNC_TYPES:
            n = node.child_by_field_name("name")
            symbols.append(CodeSymbol(
                name=_node_text(n), symbol_type="method" if parent else "function",
                start_line=node.start_point[0]+1, end_line=node.end_point[0]+1,
                parent=parent, body_text=_node_text(node),
            ))
        elif node.type in _CLASS_TYPES:
            n = node.child_by_field_name("name")
            name = _node_text(n)
            symbols.append(CodeSymbol(
                name=name, symbol_type="class",
                start_line=node.start_point[0]+1, end_line=node.end_point[0]+1,
                body_text=_node_text(node),
            ))
            for child in node.children:
                _walk(child, parent=name)
            return
        for child in node.children:
            _walk(child, parent=parent)

    _walk(root)
    return symbols


# ── Dispatch tables ───────────────────────────────────────────────────

_SYMBOL_EXTRACTORS = {
    "python": _extract_python_symbols,
    "javascript": _extract_js_symbols,
    "typescript": _extract_js_symbols,
}
_IMPORT_EXTRACTORS = {
    "python": _extract_python_imports,
    "javascript": _extract_js_imports,
    "typescript": _extract_js_imports,
}
_EXPORT_EXTRACTORS = {
    "javascript": _extract_js_exports,
    "typescript": _extract_js_exports,
}


# ── Regex fallback ────────────────────────────────────────────────────

_FUNC_RE = [
    (re.compile(r"^\s*(?:async\s+)?def\s+(\w+)"),                    "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function"),
    (re.compile(r"^\s*(?:pub\s+)?fn\s+(\w+)"),                       "function"),
    (re.compile(r"^\s*func\s+(\w+)"),                                "function"),
    (re.compile(r"^\s*class\s+(\w+)"),                               "class"),
    (re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)"),                   "class"),
]
_IMP_RE = [
    re.compile(r"^\s*(?:from\s+)?(\S+)\s+import"),
    re.compile(r"""^\s*import\s+(?:\{[^}]+\}\s+from\s+)?["']([^"']+)"""),
    re.compile(r"""^\s*(?:const|let|var)\s+\w+\s*=\s*require\(["']([^"']+)"""),
]


def _fallback_extract(text: str, language: str):
    symbols: list[CodeSymbol] = []
    imports: list[ImportInfo] = []
    for i, line in enumerate(text.splitlines()):
        for pat, stype in _FUNC_RE:
            m = pat.match(line)
            if m:
                symbols.append(CodeSymbol(name=m.group(1), symbol_type=stype,
                                          start_line=i+1, end_line=i+1))
                break
        for pat in _IMP_RE:
            m = pat.match(line)
            if m:
                imports.append(ImportInfo(source=m.group(1), line=i+1))
                break
    return symbols, imports


# ── Public API ────────────────────────────────────────────────────────

def parse_file(repo_root: Path, file_path: Path) -> FileStructure:
    """Parse a single source file and extract its structure.

    Uses Tree-sitter AST when a grammar is available, falls back to
    regex-based extraction otherwise.
    """
    text = _read_file_safely(file_path)
    if text is None:
        return FileStructure(file_path=str(file_path.relative_to(repo_root)), language="unknown")

    rel = str(file_path.relative_to(repo_root))
    ext = file_path.suffix.lower()
    lang = get_language_name(ext)
    lines = text.splitlines()
    src = text.encode("utf-8")
    parser = get_parser(ext)

    if parser is not None:
        tree = parser.parse(src)
        root = tree.root_node
        sym_fn = _SYMBOL_EXTRACTORS.get(lang, lambda r, s: _extract_generic_symbols(r, s, lang))
        symbols = sym_fn(root, src)
        imp_fn = _IMPORT_EXTRACTORS.get(lang)
        imports = imp_fn(root, src) if imp_fn else []
        exp_fn = _EXPORT_EXTRACTORS.get(lang)
        exports = exp_fn(root, src) if exp_fn else []
        return FileStructure(file_path=rel, language=lang, symbols=symbols,
                             imports=imports, exports=exports,
                             line_count=len(lines), has_ast=True, raw_text=text)
    else:
        symbols, imports = _fallback_extract(text, lang)
        return FileStructure(file_path=rel, language=lang if lang != "unknown" else ext.lstrip("."),
                             symbols=symbols, imports=imports,
                             line_count=len(lines), has_ast=False, raw_text=text)


def parse_repo(repo_root: Path, files: list[Path]) -> dict[str, FileStructure]:
    """Parse all files in a repository and return path → FileStructure."""
    return {str(f.relative_to(repo_root)): parse_file(repo_root, f) for f in files}
