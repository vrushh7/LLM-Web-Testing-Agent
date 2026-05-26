from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized settings loaded from environment variables."""

    APP_NAME: str = "HINSA AI"
    ENV: Literal["development", "staging", "production"] = "development"
    API_PREFIX: str = "/api"
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/agent.db"

    FRONTEND_ORIGINS: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://llm-web-testing-agent.vercel.app"
    )
    RATE_LIMIT_PER_MINUTE: int = 60

    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FALLBACK_MODELS: str = "gemini-2.5-flash,gemini-2.0-flash"
    GEMINI_API_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_API_URL: str = "https://api.openai.com/v1"
    AI_PROVIDER_PRIORITY: str = "gemini,openai"
    AI_TIMEOUT_SECONDS: float = 18.0
    AI_CACHE_ENABLED: bool = True

    STORAGE_DIR: Path = Path("./storage")
    REPORTS_DIR: Path = Path("./storage/reports")
    SCREENSHOTS_DIR: Path = Path("./storage/screenshots")
    SESSIONS_DIR: Path = Path("./storage/sessions")

    BROWSER_HEADLESS: bool = True
    DEFAULT_BROWSER: Literal["chromium", "firefox", "webkit"] = "chromium"
    DEFAULT_TIMEOUT_MS: int = 10000
    PRODUCTION_TIMEOUT_MS: int = 30000
    ACTION_RETRIES: int = 2
    EVIDENCE_SCREENSHOTS: bool = True
    SLOW_MO_MS: int = 0

    SECRET_KEY: str = Field(
        default="change-me-in-production",
        description="Used for future signing/encryption extensions.",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.FRONTEND_ORIGINS.split(",") if origin.strip()]

    @property
    def provider_order(self) -> list[str]:
        return [provider.strip().lower() for provider in self.AI_PROVIDER_PRIORITY.split(",") if provider.strip()]

    @property
    def gemini_model_order(self) -> list[str]:
        models = [self.GEMINI_MODEL, *self.GEMINI_FALLBACK_MODELS.split(",")]
        ordered: list[str] = []
        for model in models:
            model = model.strip()
            if model and model not in ordered:
                ordered.append(model)
        return ordered


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
