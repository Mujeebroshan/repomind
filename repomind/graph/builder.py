"""Dependency graph construction.

Builds a directed graph from AST parse results where:
- Nodes represent files, classes, functions, and directories
- Edges represent imports, declarations, and containment
- PageRank scores identify the most central / important code
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import networkx as nx

from ..parser.ast_parser import FileStructure, ImportInfo


@dataclass
class GraphNode:
    id: str
    node_type: str       # file | class | function | method | directory
    name: str
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    pagerank: float = 0.0


@dataclass
class GraphEdge:
    source: str
    target: str
    edge_type: str       # imports | declares | contains


class DependencyGraph:
    """Directed graph over the codebase with PageRank-based importance."""

    def __init__(self):
        self._graph: nx.DiGraph = nx.DiGraph()
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []

    # ── Build ──────────────────────────────────────────────────────────

    def build_from_structures(self, repo_root: Path,
                              structures: dict[str, FileStructure]) -> None:
        all_files = set(structures.keys())

        # 1. File + symbol nodes, DECLARES edges
        for rel, fs in structures.items():
            fid = f"file:{rel}"
            self._add_node(GraphNode(id=fid, node_type="file", name=Path(rel).name,
                                     file_path=rel))
            for sym in fs.symbols:
                if sym.parent:
                    continue  # methods handled below
                sid = f"symbol:{rel}:{sym.name}"
                self._add_node(GraphNode(id=sid, node_type=sym.symbol_type, name=sym.name,
                                         file_path=rel, line_start=sym.start_line,
                                         line_end=sym.end_line))
                self._add_edge(GraphEdge(source=fid, target=sid, edge_type="declares"))

        # 2. Directory nodes + CONTAINS edges
        dirs: set[str] = set()
        for rel in structures:
            parts = Path(rel).parent.parts
            for i in range(len(parts)):
                d = str(Path(*parts[: i + 1]))
                if d not in dirs:
                    dirs.add(d)
                    did = f"dir:{d}"
                    self._add_node(GraphNode(id=did, node_type="directory", name=parts[i]))
            if parts:
                self._add_edge(GraphEdge(
                    source=f"dir:{Path(rel).parent}", target=f"file:{rel}",
                    edge_type="contains"))

        # 3. IMPORTS edges
        for rel, fs in structures.items():
            src_fid = f"file:{rel}"
            for imp in fs.imports:
                target = self._resolve_import(imp, rel, all_files, fs.language)
                if target and target != rel:
                    self._add_edge(GraphEdge(source=src_fid, target=f"file:{target}",
                                             edge_type="imports"))

        # 4. PageRank
        self.compute_pagerank()

    def _resolve_import(self, imp: ImportInfo, src_file: str,
                        all_files: set[str], language: str) -> Optional[str]:
        src = imp.source
        if not src:
            return None
        src_dir = str(Path(src_file).parent)

        if language == "python":
            if src.startswith("."):
                dots = len(src) - len(src.lstrip("."))
                remainder = src[dots:]
                base = Path(src_dir)
                for _ in range(dots - 1):
                    base = base.parent
                candidates = [
                    str(base / remainder.replace(".", "/")) + ".py",
                    str(base / remainder.replace(".", "/") / "__init__.py"),
                ]
                if not remainder:
                    candidates = [str(base / "__init__.py")]
            else:
                candidates = [
                    src.replace(".", "/") + ".py",
                    src.replace(".", "/") + "/__init__.py",
                ]
        elif language in ("javascript", "typescript"):
            if src.startswith("."):
                base = str(Path(src_dir) / src)
                candidates = [base + ext for ext in (".js", ".ts", ".jsx", ".tsx", "/index.js", "/index.ts")]
                candidates.insert(0, base)
            else:
                return None  # external package
        else:
            return None

        # Normalise paths
        for c in candidates:
            norm = str(Path(c)).replace("\\", "/")
            for f in all_files:
                if f.replace("\\", "/") == norm:
                    return f
        return None

    # ── Helpers ─────────────────────────────────────────────────────────

    def _add_node(self, node: GraphNode) -> None:
        if node.id not in self._nodes:
            self._nodes[node.id] = node
            self._graph.add_node(node.id)

    def _add_edge(self, edge: GraphEdge) -> None:
        if edge.source in self._nodes and edge.target in self._nodes:
            self._edges.append(edge)
            self._graph.add_edge(edge.source, edge.target, edge_type=edge.edge_type)

    def compute_pagerank(self) -> None:
        if not self._graph.nodes:
            return
        try:
            pr = nx.pagerank(self._graph, alpha=0.85)
            for nid, score in pr.items():
                if nid in self._nodes:
                    self._nodes[nid].pagerank = score
        except nx.NetworkXError:
            pass

    # ── Query ──────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self._nodes.get(node_id)

    def get_nodes_by_type(self, node_type: str) -> list[GraphNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def get_edges_from(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self._edges if e.source == node_id]

    def get_edges_to(self, node_id: str) -> list[GraphEdge]:
        return [e for e in self._edges if e.target == node_id]

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "nodes": [asdict(n) for n in self._nodes.values()],
            "edges": [asdict(e) for e in self._edges],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyGraph":
        g = cls()
        for nd in data.get("nodes", []):
            g._add_node(GraphNode(**nd))
        for ed in data.get("edges", []):
            g._edges.append(GraphEdge(**ed))
            g._graph.add_edge(ed["source"], ed["target"], edge_type=ed["edge_type"])
        return g

    def save(self, repo_root: Path) -> None:
        d = repo_root / ".repomind"
        d.mkdir(parents=True, exist_ok=True)
        (d / "graph.json").write_text(json.dumps(self.to_dict(), indent=1))

    @classmethod
    def load(cls, repo_root: Path) -> "DependencyGraph":
        p = repo_root / ".repomind" / "graph.json"
        if p.exists():
            try:
                return cls.from_dict(json.loads(p.read_text()))
            except Exception:
                pass
        return cls()
