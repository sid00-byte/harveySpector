"""
Configuration management for HarveySpecter.

Loads settings from environment variables / .env file using pydantic-settings.
All configuration is validated at startup — if a required value is missing,
the application will refuse to start with a clear error message.
"""

from pathlib import Path
from typing import ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ───────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://harvey:harvey123@localhost:5432/harveyspecter"

    # ── Gemini / LLM ──────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "models/gemini-embedding-2"
    GEMINI_EMBEDDING_DIMENSION: int = 768

    # ── CORS ───────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000"

    # ── File uploads ───────────────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50

    # ── Allowed file types ─────────────────────────────────────────────
    ALLOWED_FILE_TYPES: ClassVar[list[str]] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "image/png",
        "image/jpeg",
        "image/tiff",
    ]

    # ── RAG tuning ─────────────────────────────────────────────────────
    RAG_TOP_K: int = 15
    RAG_RERANK_TOP_K: int = 5

    # ── Knowledge base ─────────────────────────────────────────────────
    COMPANIES_ACT_PDF_DIR: str = "./data/companies_act_2013"

    # ── Derived helpers ────────────────────────────────────────────────

    @property
    def max_file_size_bytes(self) -> int:
        """Return maximum upload size in bytes."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def upload_path(self) -> Path:
        """Ensure the upload directory exists and return it as a Path."""
        path = Path(self.UPLOAD_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must start with postgresql:// or postgres://")
        return v


# Module-level singleton — import this everywhere.
settings = Settings()
