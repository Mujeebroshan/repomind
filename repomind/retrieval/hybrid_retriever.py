"""Hybrid retrieval combining vector search, dependency graph, and knowledge base."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..indexer import get_collection, has_index
from ..understanding.knowledge_base import KnowledgeBase
from ..graph.builder import DependencyGraph
from ..graph.query import get_file_dependents, get_file_dependencies


@dataclass
class RetrievalResult:
    file_path: str
    start_line: int = 0
    end_line: int = 0
    text: str = ""
    source: str = ""  # vector | knowledge_base | graph
    score: float = 0.0


@dataclass
class RetrievalContext:
    code_chunks: list[RetrievalResult] = field(default_factory=list)
    file_summaries: list[str] = field(default_factory=list)
    directory_context: str = ""
    project_context: str = ""
    repo_map: str = ""


async def hybrid_retrieve(
    repo_root: Path,
    question: str,
    local_provider,
    top_k: int = 8,
    use_graph: bool = True,
    use_knowledge_base: bool = True,
) -> RetrievalContext:
    """Combine vector search, knowledge base, and graph for rich retrieval."""
    ctx = RetrievalContext()

    # 1. Vector search via ChromaDB
    try:
        if has_index(repo_root):
            collection = get_collection(repo_root)
            # Embed the question
            embeddings = local_provider.embed([question])
            results = collection.query(
                query_embeddings=embeddings,
                n_results=top_k,
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            for i, doc in enumerate(docs):
                meta = metas[i] if i < len(metas) else {}
                dist = dists[i] if i < len(dists) else 1.0
                ctx.code_chunks.append(RetrievalResult(
                    file_path=meta.get("file", ""),
                    start_line=meta.get("start_line", 0),
                    end_line=meta.get("end_line", 0),
                    text=doc,
                    source="vector",
                    score=1.0 - dist,  # ChromaDB returns distances
                ))
    except Exception:
        pass  # gracefully skip if no vector index

    # 2. Knowledge base context
    if use_knowledge_base:
        try:
            kb = KnowledgeBase.load(repo_root)
            matched_files = set(r.file_path for r in ctx.code_chunks if r.file_path)

            # File summaries for matched files
            for fp in matched_files:
                fs = kb.get_file_summary(fp)
                if fs:
                    ctx.file_summaries.append(f"[{fp}] {fs.get('summary', '')}")

            # Parent directory context
            parent_dirs = set()
            for fp in matched_files:
                parent_dirs.add(str(Path(fp).parent))
            dir_parts = []
            for d in parent_dirs:
                ds = kb.get_directory_summary(d)
                if ds:
                    dir_parts.append(f"[{d}] {ds.get('summary', '')}")
            ctx.directory_context = "\n".join(dir_parts)

            # Project overview snippet
            overview = kb.get_project_overview()
            if overview:
                ctx.project_context = overview.get("summary", "")[:300]

            # Search KB for additional relevant summaries
            kb_results = kb.search_summaries(question)
            for res in kb_results[:5]:
                fp = res.get("path", "")
                if fp and fp not in matched_files:
                    ctx.file_summaries.append(f"[{fp}] {res.get('summary', '')}")
        except Exception:
            pass

    # 3. Graph-based expansion
    if use_graph:
        try:
            graph = DependencyGraph.load(repo_root)
            matched_files = set(r.file_path for r in ctx.code_chunks if r.file_path)
            for fp in list(matched_files)[:5]:
                deps = get_file_dependencies(graph, fp)
                dependents = get_file_dependents(graph, fp)
                related = set(deps[:3] + dependents[:3]) - matched_files
                for rel_fp in related:
                    try:
                        kb = KnowledgeBase.load(repo_root)
                        fs = kb.get_file_summary(rel_fp)
                        if fs:
                            ctx.file_summaries.append(
                                f"[related: {rel_fp}] {fs.get('summary', '')}")
                    except Exception:
                        pass
        except Exception:
            pass

    # 4. Repo map
    try:
        from .repo_map import generate_repo_map
        ctx.repo_map = generate_repo_map(repo_root, max_tokens=1500)
    except Exception:
        pass

    return ctx
