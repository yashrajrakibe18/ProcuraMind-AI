"""Single validated settings module. All configuration comes from environment variables."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ProcureAI"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_allowed_origins: str = "http://localhost:8501"
    log_level: str = "INFO"

    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 480
    allow_registration: bool = True

    database_url: str = "sqlite:///./storage/procureai.db"
    vector_store_path: str = "./storage/chroma"
    document_storage_path: str = "./storage/documents"
    max_upload_size_mb: int = 25

    llm_provider: str = "none"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    embedding_model: str = "hashing-v1"
    embedding_dim: int = 512

    base_currency: str = "USD"
    fx_rates_json: str = '{"USD":1.0,"EUR":1.08,"GBP":1.27,"INR":0.012}'
    rag_min_score: float = Field(default=0.12, ge=0.0, le=1.0)
    chunk_target_tokens: int = 220
    chunk_overlap_tokens: int = 40
    workflow_step_max_retries: int = 2
    workflow_step_timeout_seconds: float = 120.0
    ocr_min_chars_per_page: int = 25
    max_pdf_pages: int = 300
    price_threshold_pct: float = 25.0
    min_history_for_ml: int = 30
    allowed_extensions: str = ".pdf,.txt,.csv,.md,.png,.jpg,.jpeg,.docx,.xlsx"
    auto_create_tables: bool = True
    scheduler_enabled: bool = False
    allow_private_webhooks: bool = False

    @field_validator("log_level")
    @classmethod
    def _upper_level(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.app_env.lower() == "production" and (
            self.secret_key == "change-me-in-production" or len(self.secret_key) < 32
        ):
            raise ValueError("SECRET_KEY must be set to a strong random value (>= 32 chars) in production")
        return self

    @property
    def extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def fx_rates(self) -> dict[str, float]:
        try:
            raw = json.loads(self.fx_rates_json)
            return {str(k).upper(): float(v) for k, v in raw.items()}
        except (ValueError, TypeError):
            return {"USD": 1.0}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def ensure_directories(self) -> None:
        Path(self.document_storage_path).mkdir(parents=True, exist_ok=True)
        Path(self.vector_store_path).mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.replace("sqlite:///", "", 1))
            if str(db_path) not in ("", ":memory:"):
                db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
