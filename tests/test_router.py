"""Router fallback logic tested against stub providers - never touches Gemini/Ollama for real."""

import pytest

from personal_llm.router.providers import RouterError
from personal_llm.router.router import ModelRouter
from personal_llm.router.schemas import Completion, Message


class _StubProvider:
    def __init__(self, name, available=True, raises=False, text="ok"):
        self.name = name
        self._available = available
        self._raises = raises
        self.text = text
        self.called = False
        self.availability_checks = 0

    def is_available(self):
        self.availability_checks += 1
        return self._available

    def complete(self, messages, schema=None):
        self.called = True
        if self._raises:
            raise RouterError(f"{self.name} failed")
        return Completion(text=self.text, parsed=None, provider=self.name, model="stub")


def test_router_uses_first_available_provider():
    p1 = _StubProvider("p1", text="from p1")
    p2 = _StubProvider("p2", text="from p2")
    router = ModelRouter(chat_providers=[p1, p2])

    result = router.complete([Message(role="user", content="hi")])

    assert result.text == "from p1"
    assert p2.called is False


def test_router_falls_back_when_first_unavailable():
    p1 = _StubProvider("p1", available=False)
    p2 = _StubProvider("p2", text="from p2")
    router = ModelRouter(chat_providers=[p1, p2])

    result = router.complete([Message(role="user", content="hi")])

    assert result.text == "from p2"


def test_router_falls_back_on_provider_error():
    p1 = _StubProvider("p1", raises=True)
    p2 = _StubProvider("p2", text="from p2")
    router = ModelRouter(chat_providers=[p1, p2])

    result = router.complete([Message(role="user", content="hi")])

    assert result.text == "from p2"


def test_router_raises_when_nothing_available():
    p1 = _StubProvider("p1", available=False)
    router = ModelRouter(chat_providers=[p1])

    with pytest.raises(RouterError):
        router.complete([Message(role="user", content="hi")])


def test_router_caches_ollama_health_check():
    stub = _StubProvider("ollama", text="ollama-answer")
    router = ModelRouter(chat_providers=[stub])

    router.complete([Message(role="user", content="hi")])
    router.complete([Message(role="user", content="hi again")])

    assert stub.availability_checks == 1  # health-checked once, then cached


def test_router_embed_uses_injected_embedder():
    class _FakeEmbedder:
        def embed(self, texts):
            return [[1.0, 2.0] for _ in texts]

    router = ModelRouter(chat_providers=[], embedder=_FakeEmbedder())

    result = router.embed(["a", "b"])

    assert result == [[1.0, 2.0], [1.0, 2.0]]


class _FixedEmbedder:
    def __init__(self, vectors: dict):
        self._vectors = vectors

    def embed(self, texts):
        return [self._vectors[t] for t in texts]


def test_verification_agrees_when_texts_are_similar():
    p1 = _StubProvider("p1", text="paris")
    p2 = _StubProvider("p2", text="paris is the capital")
    embedder = _FixedEmbedder({"paris": [1.0, 0.0], "paris is the capital": [0.95, 0.05]})
    router = ModelRouter(chat_providers=[p1, p2], embedder=embedder)

    result = router.complete_with_verification([Message(role="user", content="capital of france?")])

    assert result.primary.text == "paris"
    assert result.alternates[0].text == "paris is the capital"
    assert not result.disagreement
    assert result.agreement_scores[0] > 0.6


def test_verification_flags_disagreement_when_texts_diverge():
    p1 = _StubProvider("p1", text="yes")
    p2 = _StubProvider("p2", text="no")
    embedder = _FixedEmbedder({"yes": [1.0, 0.0], "no": [0.0, 1.0]})
    router = ModelRouter(chat_providers=[p1, p2], embedder=embedder)

    result = router.complete_with_verification([Message(role="user", content="q")])

    assert result.disagreement
    assert result.agreement_scores[0] == pytest.approx(0.0)


def test_verification_single_provider_has_no_alternates():
    p1 = _StubProvider("p1", text="only answer")
    router = ModelRouter(chat_providers=[p1])

    result = router.complete_with_verification([Message(role="user", content="q")])

    assert result.alternates == []
    assert result.agreement_scores == []
    assert not result.disagreement


def test_verification_skips_unavailable_provider():
    p1 = _StubProvider("p1", available=False)
    p2 = _StubProvider("p2", text="only from p2")
    router = ModelRouter(chat_providers=[p1, p2])

    result = router.complete_with_verification([Message(role="user", content="q")])

    assert result.primary.text == "only from p2"
    assert result.alternates == []


def test_verification_raises_when_nothing_available():
    p1 = _StubProvider("p1", available=False)
    router = ModelRouter(chat_providers=[p1])

    with pytest.raises(RouterError):
        router.complete_with_verification([Message(role="user", content="q")])


def test_provider_status_reports_each_provider():
    p1 = _StubProvider("p1", available=True)
    p2 = _StubProvider("p2", available=False)
    router = ModelRouter(chat_providers=[p1, p2])

    status = router.provider_status()

    assert status == {"p1": True, "p2": False}
