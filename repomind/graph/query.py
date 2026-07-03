"""Query interface for the dependency graph."""
from __future__ import annotations

from .builder import DependencyGraph, GraphNode


def get_file_dependencies(graph: DependencyGraph, file_path: str) -> list[str]:
    """Files that *file_path* imports from."""
    nid = f"file:{file_path}"
    return [e.target.removeprefix("file:") for e in graph.get_edges_from(nid)
            if e.edge_type == "imports"]


def get_file_dependents(graph: DependencyGraph, file_path: str) -> list[str]:
    """Files that import from *file_path*."""
    nid = f"file:{file_path}"
    return [e.source.removeprefix("file:") for e in graph.get_edges_to(nid)
            if e.edge_type == "imports"]


def get_related_context(graph: DependencyGraph, node_id: str,
                        depth: int = 2) -> list[GraphNode]:
    """BFS to get nodes within *depth* hops."""
    visited: set[str] = set()
    queue = [(node_id, 0)]
    results: list[GraphNode] = []
    while queue:
        nid, d = queue.pop(0)
        if nid in visited or d > depth:
            continue
        visited.add(nid)
        node = graph.get_node(nid)
        if node and nid != node_id:
            results.append(node)
        if d < depth:
            for e in graph.get_edges_from(nid) + graph.get_edges_to(nid):
                other = e.target if e.source == nid else e.source
                queue.append((other, d + 1))
    return results


def get_most_important_files(graph: DependencyGraph,
                             top_n: int = 20) -> list[tuple[str, float]]:
    """Top-N files ranked by PageRank."""
    ranked = sorted(graph.get_nodes_by_type("file"),
                    key=lambda n: n.pagerank, reverse=True)
    return [(n.file_path, n.pagerank) for n in ranked[:top_n]]


def get_directory_files(graph: DependencyGraph, dir_path: str) -> list[GraphNode]:
    """All file nodes in a directory."""
    did = f"dir:{dir_path}"
    return [graph.get_node(e.target) for e in graph.get_edges_from(did)
            if e.edge_type == "contains" and graph.get_node(e.target)]
