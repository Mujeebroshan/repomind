from __future__ import annotations

import uuid
from pathlib import Path

import chromadb

from .chunking import Chunk, chunk_repo
from .config import WorkspaceSettings, workspace_data_dir
from .models import IndexStatus
from .providers.registry import build_local_provider

EMBED_BATCH_SIZE = 16

# In-memory progress, keyed by resolved repo path. Fine for a single-user
# local tool; a hosted/team version would move this to a real job table.
_INDEX_JOBS: dict[str, IndexStatus] = {}


def _job_key(repo_root: Path) -> str:
    return str(repo_root.resolve())


def get_index_status(repo_root: Path) -> IndexStatus:
    return _INDEX_JOBS.get(_job_key(repo_root), IndexStatus())


def get_chroma_client(repo_root: Path) -> chromadb.ClientAPI:
    persist_dir = workspace_data_dir(repo_root) / "chroma"
    return chromadb.PersistentClient(path=str(persist_dir))


def _reset_collection(repo_root: Path):
    client = get_chroma_client(repo_root)
    try:
        client.delete_collection("repomind")
    except Exception:
        pass
    return client.get_or_create_collection("repomind", metadata={"hnsw:space": "cosine"})


def get_collection(repo_root: Path):
    client = get_chroma_client(repo_root)
    return client.get_or_create_collection("repomind", metadata={"hnsw:space": "cosine"})


def has_index(repo_root: Path) -> bool:
    try:
        return get_collection(repo_root).count() > 0
    except Exception:
        return False


async def index_repo(repo_root: Path, settings: WorkspaceSettings) -> IndexStatus:
    key = _job_key(repo_root)
    status = IndexStatus(state="scanning")
    _INDEX_JOBS[key] = status

    try:
        files, chunks = chunk_repo(repo_root)
        status.files_total = len(files)
        status.state = "embedding"

        collection = _reset_collection(repo_root)
        embedder = build_local_provider(settings)

        files_seen: set[str] = set()
        for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch: list[Chunk] = chunks[batch_start : batch_start + EMBED_BATCH_SIZE]
            if not batch:
                continue
            texts = [c.text for c in batch]
            vectors = await embedder.embed(texts)

            ids = [str(uuid.uuid4()) for _ in batch]
            metadatas = [
                {"file_path": c.file_path, "start_line": c.start_line, "end_line": c.end_line}
                for c in batch
            ]
            collection.add(ids=ids, embeddings=vectors, documents=texts, metadatas=metadatas)

            status.chunks_indexed += len(batch)
            for c in batch:
                files_seen.add(c.file_path)
            status.files_done = len(files_seen)

        status.state = "done"
        return status
    except Exception as exc:  # surfaced to the UI rather than a bare 500
        status.state = "error"
        status.error = str(exc)
        return status
    finally:
        _INDEX_JOBS[key] = status
