"""Central configuration, loaded from environment / .env via pydantic-settings.

All persisted data lives under one absolute root (`NEXUS_DATA_DIR`, default
`C:\\Users\\Asus\\projects\\ai-ecosystem\\data` - the ecosystem-level data dir, not
personal-llm's own). Historically the db/chroma/workspace/voice paths were each their
own CWD-relative field ("./data/..."), which meant the exact same code produced a
different store depending on which directory it was launched from - the direct cause of
three diverged SQLite DBs and three diverged Chroma dirs. They are now read-only
properties derived from a single root, not independently settable fields, so there is no
way to reintroduce the divergence. `.env` may still carry the old
`PERSONAL_LLM_DATA_DIR=./data`-style keys from before this change; `extra="ignore"`
means they are silently ignored rather than reintroducing CWD-relative paths.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATA_ROOT = Path(r"C:\Users\Asus\projects\ai-ecosystem\data")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    embedding_model: str = "all-MiniLM-L6-v2"

    # Single root every data path derives from. Env var: NEXUS_DATA_DIR. Must be
    # absolute if set at all - see _require_absolute below.
    nexus_data_dir: str | None = None

    night_shift_log_path: str = "../NIGHT_SHIFT.md"

    retrieval_top_k: int = 8
    retrieval_min_similarity: float = 0.25
    memory_recency_half_life_days: float = 30.0

    agent_max_steps: int = 6
    whisper_model_size: str = "base"

    @field_validator("nexus_data_dir")
    @classmethod
    def _require_absolute(cls, value: str | None) -> str | None:
        if value is not None and not Path(value).is_absolute():
            raise ValueError(
                f"NEXUS_DATA_DIR must be an absolute path, got {value!r}."
            )
        return value

    @property
    def data_root(self) -> Path:
        return Path(self.nexus_data_dir) if self.nexus_data_dir else DEFAULT_DATA_ROOT

    @property
    def personal_llm_data_dir(self) -> str:
        return str(self.data_root)

    @property
    def personal_llm_db_path(self) -> str:
        return str(self.data_root / "personal_llm.db")

    @property
    def personal_llm_chroma_dir(self) -> str:
        return str(self.data_root / "chroma")

    @property
    def personal_llm_workspace_dir(self) -> str:
        return str(self.data_root / "workspace")

    @property
    def personal_llm_voice_dir(self) -> str:
        return str(self.data_root / "voice")

    @property
    def personal_llm_gateway_token_path(self) -> str:
        return str(self.data_root / "gateway_token")

    def ensure_data_dirs(self) -> None:
        Path(self.personal_llm_data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.personal_llm_chroma_dir).mkdir(parents=True, exist_ok=True)
        Path(self.personal_llm_db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.personal_llm_workspace_dir).mkdir(parents=True, exist_ok=True)
        Path(self.personal_llm_voice_dir).mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_data_dirs()
    return _settings


def reset_settings() -> None:
    """Clear the cached singleton so a changed NEXUS_DATA_DIR (or other env var) takes
    effect on the next `get_settings()` call. Test-only - production code never needs
    to reload settings mid-process."""
    global _settings
    _settings = None
