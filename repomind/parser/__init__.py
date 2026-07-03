"""AST-aware code parsing and smart chunking."""
from .ast_parser import parse_file, parse_repo, FileStructure, CodeSymbol, ImportInfo
from .smart_chunker import smart_chunk_file, smart_chunk_repo, SmartChunk
from .languages import LANGUAGE_MAP, get_language_name, supported_extensions
