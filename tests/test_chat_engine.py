import pytest

from codechat import chat_engine, indexer
from codechat.config import EnvDefaults, WorkspaceSettings
from tests.fakes import FakeFrontierProvider, FakeOllamaProvider


async def make_indexed_repo(tmp_path, monkeypatch):
    fake = FakeOllamaProvider()
    monkeypatch.setattr(indexer, "build_local_provider", lambda settings: fake)
    (tmp_path / "billing.py").write_text(
        "def calculate_total(items):\n    return sum(i.price for i in items)\n"
    )
    settings = WorkspaceSettings.from_env(EnvDefaults())
    await indexer.index_repo(tmp_path, settings)
    return settings


async def collect_events(repo, settings, question, mode):
    events = []
    async for event in chat_engine.run_chat(repo, settings, question, [], mode):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_chat_errors_when_repo_not_indexed(tmp_path):
    settings = WorkspaceSettings.from_env(EnvDefaults())
    events = await collect_events(tmp_path, settings, "what does this do?", "auto")
    assert events[0]["type"] == "error"
    assert "indexed" in events[0]["message"]


@pytest.mark.asyncio
async def test_local_only_mode_never_calls_frontier(tmp_path, monkeypatch):
    settings = await make_indexed_repo(tmp_path, monkeypatch)
    local = FakeOllamaProvider(answer_reply="this sums item prices")
    monkeypatch.setattr(chat_engine, "build_local_provider", lambda s: local)

    def fail_if_called(provider_id, s):
        raise AssertionError("frontier provider should not be built in local_only mode")

    monkeypatch.setattr(chat_engine, "build_frontier_provider", fail_if_called)

    events = await collect_events(tmp_path, settings, "what does calculate_total do?", "local_only")
    route_event = next(e for e in events if e["type"] == "route")
    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    done_event = next(e for e in events if e["type"] == "done")

    assert route_event["route"] == "local"
    assert tokens == "this sums item prices"
    assert done_event["provider"] == "ollama"
    assert done_event["local_count"] == 1


@pytest.mark.asyncio
async def test_escalate_only_mode_uses_frontier_provider(tmp_path, monkeypatch):
    settings = await make_indexed_repo(tmp_path, monkeypatch)
    local = FakeOllamaProvider()
    frontier = FakeFrontierProvider(reply="a more careful architectural answer", configured=True)
    monkeypatch.setattr(chat_engine, "build_local_provider", lambda s: local)
    monkeypatch.setattr(chat_engine, "build_frontier_provider", lambda pid, s: frontier)

    events = await collect_events(tmp_path, settings, "how should I refactor this?", "escalate_only")
    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    done_event = next(e for e in events if e["type"] == "done")

    assert tokens == "a more careful architectural answer"
    assert done_event["route"] == "escalate"
    assert done_event["escalated_count"] == 1


@pytest.mark.asyncio
async def test_auto_mode_escalates_when_router_says_complex(tmp_path, monkeypatch):
    settings = await make_indexed_repo(tmp_path, monkeypatch)
    local = FakeOllamaProvider(route_reply="COMPLEX")
    frontier = FakeFrontierProvider(reply="cloud says: refactor like this", configured=True)
    monkeypatch.setattr(chat_engine, "build_local_provider", lambda s: local)
    monkeypatch.setattr(chat_engine, "build_frontier_provider", lambda pid, s: frontier)

    events = await collect_events(tmp_path, settings, "what's the best way to restructure this module?", "auto")
    route_event = next(e for e in events if e["type"] == "route")
    assert route_event["route"] == "escalate"
    assert route_event["router_was_local"] is True


@pytest.mark.asyncio
async def test_escalation_degrades_to_local_when_frontier_not_configured(tmp_path, monkeypatch):
    settings = await make_indexed_repo(tmp_path, monkeypatch)
    local = FakeOllamaProvider(answer_reply="answered locally instead")
    frontier = FakeFrontierProvider(configured=False)
    monkeypatch.setattr(chat_engine, "build_local_provider", lambda s: local)
    monkeypatch.setattr(chat_engine, "build_frontier_provider", lambda pid, s: frontier)

    events = await collect_events(tmp_path, settings, "anything", "escalate_only")
    notice = next(e for e in events if e["type"] == "notice")
    done_event = next(e for e in events if e["type"] == "done")

    assert "isn't configured" in notice["message"]
    assert done_event["route"] == "local"
