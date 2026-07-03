import pytest

from codechat import router
from codechat.providers.base import ProviderError
from tests.fakes import FakeOllamaProvider


@pytest.mark.asyncio
async def test_classify_uses_local_model_when_it_says_simple():
    local = FakeOllamaProvider(route_reply="SIMPLE")
    verdict, used_local = await router.classify(local, "where is parse_config defined?", ["config.py"])
    assert verdict == "SIMPLE"
    assert used_local is True


@pytest.mark.asyncio
async def test_classify_uses_local_model_when_it_says_complex():
    local = FakeOllamaProvider(route_reply="COMPLEX")
    verdict, used_local = await router.classify(local, "how should I refactor this module?", ["app.py"])
    assert verdict == "COMPLEX"
    assert used_local is True


@pytest.mark.asyncio
async def test_classify_falls_back_to_heuristic_when_local_unreachable():
    class BrokenProvider(FakeOllamaProvider):
        async def chat_stream(self, messages, system=None, temperature=0.2):
            raise ProviderError("connection refused")
            yield ""  # pragma: no cover -- unreachable, keeps this an async generator

    local = BrokenProvider()
    verdict, used_local = await router.classify(local, "should I refactor this for performance?", [])
    assert verdict == "COMPLEX"  # heuristic catches "refactor" / "performance"
    assert used_local is False


def test_heuristic_classify_simple_vs_complex():
    assert router.heuristic_classify("what does this function return?") == "SIMPLE"
    assert router.heuristic_classify("what's the best architecture for scaling this?") == "COMPLEX"
