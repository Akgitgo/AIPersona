from functools import lru_cache
from typing import List
from pydantic import field_validator
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── LLM ──────────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str | None = None
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    CLAUDE_MAX_TOKENS: int = 1024

    # ── Embeddings ───────────────────────────────────────────────────────────
    OPENAI_API_KEY: str
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # ── Vector Store ─────────────────────────────────────────────────────────
    QDRANT_URL: str
    QDRANT_API_KEY: str
    QDRANT_COLLECTION: str = "persona_knowledge"

    # ── Voice (Vapi) ─────────────────────────────────────────────────────────
    VAPI_API_KEY: str = ""
    VAPI_PHONE_NUMBER_ID: str = ""
    VAPI_ASSISTANT_ID: str = ""

    # ── Calendar (Cal.com) ───────────────────────────────────────────────────
    CALCOM_API_KEY: str = ""
    CALCOM_EVENT_TYPE_SLUG: str = "30min"
    CALCOM_USERNAME: str = ""

    # ── GitHub ───────────────────────────────────────────────────────────────
    GITHUB_TOKEN: str = ""
    GITHUB_USERNAME: str = ""

    # ── App ──────────────────────────────────────────────────────────────────
    API_BASE_URL: str = "http://localhost:8000"
    CORS_ORIGINS: str = "http://localhost:3000"
    INGEST_SECRET: str = "changeme"

    # RAG retrieval knobs
    RAG_TOP_K: int = 6
    RAG_SCORE_THRESHOLD: float = 0.35
    RAG_CHUNK_SIZE: int = 512
    RAG_CHUNK_OVERLAP: int = 64

    # Conversation history window (message pairs kept)
    HISTORY_WINDOW: int = 6

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, v: str) -> str:
        return v  # kept as str; parsed on use

    def get_cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
