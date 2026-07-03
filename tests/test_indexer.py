import pytest

from codechat import indexer
from codechat.config import EnvDefaults, WorkspaceSettings
from tests.fakes import FakeOllamaProvider


def make_repo(tmp_path):
    (tmp_path / "app.py").write_text(
        "def calculate_total(items):\n    return sum(i.price for i in items)\n\n"
        "def calculate_tax(total, rate):\n    return total * rate\n"
    )
    (tmp_path / "utils.py").write_text("def slugify(text):\n    return text.lower().replace(' ', '-')\n")
    return tmp_path


@pytest.mark.asyncio
async def test_index_repo_populates_collection(tmp_path, monkeypatch):
    fake = FakeOllamaProvider()
    monkeypatch.setattr(indexer, "build_local_provider", lambda settings: fake)
    repo = make_repo(tmp_path)
    settings = WorkspaceSettings.from_env(EnvDefaults())

    status = await indexer.index_repo(repo, settings)

    assert status.state == "done"
    assert status.chunks_indexed >= 2
    assert indexer.has_index(repo) is True

    collection = indexer.get_collection(repo)
    assert collection.count() == status.chunks_indexed


@pytest.mark.asyncio
async def test_index_repo_reports_error_state_on_failure(tmp_path, monkeypatch):
    class FailingProvider(FakeOllamaProvider):
        async def embed(self, texts):
            raise RuntimeError("boom")

    monkeypatch.setattr(indexer, "build_local_provider", lambda settings: FailingProvider())
    repo = make_repo(tmp_path)
    settings = WorkspaceSettings.from_env(EnvDefaults())

    status = await indexer.index_repo(repo, settings)
    assert status.state == "error"
    assert "boom" in status.error
