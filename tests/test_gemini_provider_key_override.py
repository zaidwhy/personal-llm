"""GeminiProvider's per-instance api_key override, added for the public HF Space demo
(space/app.py) where each visitor supplies their own key and it must never leak into a
process-wide setting shared with other visitors."""

from __future__ import annotations

from personal_llm.router.providers import GeminiProvider


def test_defaults_to_settings_key_when_no_override_given(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    from personal_llm import config

    config.reset_settings()
    provider = GeminiProvider()
    assert provider.is_available()
    assert provider._api_key == "from-env"
    config.reset_settings()


def test_override_key_wins_over_settings(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    from personal_llm import config

    config.reset_settings()
    provider = GeminiProvider(api_key="visitor-supplied-key")
    assert provider._api_key == "visitor-supplied-key"
    config.reset_settings()


def test_is_available_true_with_only_an_override_and_no_env_key(monkeypatch):
    # An empty string, not delenv: pydantic-settings still reads a real key from this
    # machine's .env file even after delenv removes the process environment variable.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from personal_llm import config

    config.reset_settings()
    provider = GeminiProvider(api_key="visitor-supplied-key")
    assert provider.is_available()
    config.reset_settings()


def test_is_available_false_with_neither_override_nor_env_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from personal_llm import config

    config.reset_settings()
    provider = GeminiProvider()
    assert not provider.is_available()
    config.reset_settings()


def test_two_instances_with_different_keys_never_share_state(monkeypatch):
    """The regression this override exists to prevent: two providers built for two
    different visitors in the same process must never read each other's key."""
    monkeypatch.setenv("GEMINI_API_KEY", "process-wide-fallback")
    from personal_llm import config

    config.reset_settings()
    provider_a = GeminiProvider(api_key="visitor-a-key")
    provider_b = GeminiProvider(api_key="visitor-b-key")
    assert provider_a._api_key == "visitor-a-key"
    assert provider_b._api_key == "visitor-b-key"
    config.reset_settings()
