"""Central configuration, loaded from environment / .env via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    embedding_model: str = "all-MiniLM-L6-v2"

    personal_llm_data_dir: str = "./data"
    personal_llm_db_path: str = "./data/personal_llm.db"
    personal_llm_chroma_dir: str = "./data/chroma"
    personal_llm_workspace_dir: str = "./data/workspace"
    personal_llm_voice_dir: str = "./data/voice"

    retrieval_top_k: int = 8
    retrieval_min_similarity: float = 0.25
    memory_recency_half_life_days: float = 30.0

    agent_max_steps: int = 6
    whisper_model_size: str = "base"

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
