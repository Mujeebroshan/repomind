"""Codebase dependency graph construction and querying."""
from .builder import DependencyGraph, GraphNode, GraphEdge
from .query import (get_file_dependencies, get_file_dependents,
                    get_related_context, get_most_important_files)
