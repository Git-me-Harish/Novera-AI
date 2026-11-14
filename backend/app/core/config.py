""" Core configuration module using Pydantic settings management with validation and type safety."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import List, Optional, Union

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation and type safety."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application:
    app_name: str = "Novera AI Knowledge Assistant"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    # Server:
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    # Database:
    database_url: str = Field(..., description="Async PostgreSQL connection URL")
    database_pool_size: int = Field(default=20, ge=5)   # FIX: minimum 5
    database_max_overflow: int = 10

    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_db: Optional[str] = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @property
    def sync_database_url(self) -> str:
        """
        Synchronous database URL for Alembic / psycopg2 operations.
        Handles all common async-driver URL variants.
        """
        url = self.database_url
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        url = url.replace("postgres+asyncpg://", "postgresql+psycopg2://")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://") and "+psycopg2" not in url:
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    # Redis:
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600
    embedding_cache_ttl_seconds: int = Field(default=3600, ge=30, le=86400)
    semantic_cache_enabled: bool = True
    semantic_cache_ttl_seconds: int = Field(default=300, ge=30, le=86400)
    semantic_cache_similarity_threshold: float = Field(default=0.96, ge=0.0, le=1.0)
    document_queue_max_attempts: int = Field(default=5, ge=1, le=20)
    document_queue_retry_base_seconds: int = Field(default=30, ge=1, le=3600)
    document_queue_retry_max_seconds: int = Field(default=900, ge=1, le=86400)

    # ── AI models (provider-agnostic) ────────────────────────────────────
    # No model is hardcoded. Providers come from app.services.ai.catalog
    # (openai, azure_openai, anthropic, gemini, mistral, groq, together,
    # deepseek, xai, openrouter, fireworks, cohere, jina, voyage, ollama,
    # vllm, lmstudio, openai_compatible). Tenants may override chat models.
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    # Comma-separated "provider:model" entries tried in order on outage.
    llm_fallback_models: str = ""
    # Cheaper model for titles/suggestions; empty = use llm_model.
    llm_utility_model: Optional[str] = None

    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None
    # Must equal the chunks.embedding vector column size. Changing the model
    # or size requires re-embedding the corpus, never padding.
    embedding_dimensions: int = 1536
    embedding_batch_size: int = Field(default=64, ge=1, le=512)
    # JSON object of adapter options, e.g. {"input_type_param": "input_type"}.
    embedding_options: str = "{}"

    # "none" disables reranking explicitly.
    rerank_provider: Optional[str] = None
    rerank_model: Optional[str] = None
    rerank_api_key: Optional[str] = None
    rerank_base_url: Optional[str] = None

    # Per-provider credentials, used by fallbacks and tenant settings that
    # pick a provider without supplying their own key.
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    cohere_api_key: Optional[str] = None

    # Tenant-supplied model endpoints are fetched by this server. By default
    # they must be public HTTPS hosts (SSRF protection). Enable only for
    # single-company deployments that use on-prem models (e.g. Ollama).
    ai_allow_private_tenant_endpoints: bool = False

    # JSON price table, see app.services.ai.pricing. Empty = costs unknown.
    llm_pricing: str = "{}"

    # Key for encrypting tenant-supplied API keys at rest. Defaults to a key
    # derived from SECRET_KEY; set explicitly to rotate independently.
    ai_secrets_key: Optional[str] = None

    # Legacy single-vendor settings, still honoured when the generic ones
    # are unset so existing deployments keep working.
    gemini_embedding_model: Optional[str] = None
    gemini_embedding_dimensions: Optional[int] = None
    gemini_chat_model: Optional[str] = None
    cohere_rerank_model: Optional[str] = None

    # Offline evaluation judge. A stronger model than the generator limits
    # self-preference bias; it is never called on the request path.
    eval_judge_provider: Optional[str] = None
    eval_judge_model: Optional[str] = None

    # JWT Authentication:
    secret_key: str = Field(..., min_length=32, description="JWT signing secret (min 32 chars)")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # Email:
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_email: str = Field(default="")
    smtp_from_name: str = Field(default="Novera AI")
    smtp_use_tls: bool = Field(default=True)

    # Password Reset:
    password_reset_token_expire_minutes: int = Field(default=15)
    frontend_url: str = Field(default="http://localhost:5173")

    # Document Processing:
    max_upload_size_mb: int = 50
    allowed_extensions: str = "pdf,docx,doc,txt,xlsx,xls"
    upload_dir: str = "./data/uploads"
    processed_dir: str = "./data/processed"

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip() for ext in self.allowed_extensions.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    # Chunking:
    chunk_size: int = 800
    chunk_overlap: int = 150
    max_table_tokens: int = 2000
    min_chunk_size: int = 100

    # Retrieval:
    retrieval_top_k: int = 30
    rerank_top_k: int = 12
    similarity_threshold: float = 0.3
    hybrid_alpha: float = 0.7
    global_search_top_k: int = Field(default=20)
    scoped_search_top_k: int = Field(default=12)
    min_rerank_score: float = Field(default=0.2, ge=0.0, le=1.0)
    focused_context_chunks: int = Field(default=3, ge=1, le=20)
    complex_context_chunks: int = Field(default=5, ge=1, le=30)

    enable_dynamic_scope: bool = Field(default=True)
    min_relevance_for_scoped_search: float = Field(default=0.5)

    # Generation:
    max_context_tokens: int = 12000
    # Factual document QA benefits from deterministic decoding and a bounded
    # answer budget. Longer analytical answers can be enabled explicitly via
    # environment configuration without making the default path expensive.
    temperature: float = 0.0
    max_response_tokens: int = 800
    llm_max_concurrency: int = Field(default=4, ge=1, le=32)
    llm_answer_timeout_seconds: int = Field(default=12, ge=2, le=60)
    llm_attempt_timeout_seconds: int = Field(default=6, ge=1, le=30)

    # Guardrails:
    enable_input_guardrails: bool = True
    enable_output_guardrails: bool = True
    hallucination_threshold: float = 0.3

    # Query Classification:
    enable_llm_classification: bool = Field(default=True)
    classification_cache_ttl: int = Field(default=3600)

    # Context Management:
    context_timeout_hours: int = Field(default=1)
    context_max_documents: int = Field(default=5)
    context_boost_factor: float = Field(default=1.5)
    enable_query_reformulation: bool = Field(default=True)
    enable_context_ui: bool = Field(default=True)

    # Tenancy:
    # invite_only: org admins invite people (default, safe for shared tenants)
    # self_serve:  sign-up creates a NEW organization owned by the new user
    # disabled:    no sign-up; super admins provision everything
    # Sign-up never places a stranger inside an existing organization.
    registration_mode: str = Field(default="invite_only", pattern="^(invite_only|self_serve|disabled)$")
    invitation_expire_days: int = Field(default=7, ge=1, le=90)
    audit_retention_days: int = Field(default=365, ge=30, le=3650)
    # Per-organization request limits (per minute unless noted); an
    # organization can be given different values by a super admin.
    org_rate_limit_chat_per_minute: int = Field(default=600, ge=1)
    org_rate_limit_upload_per_minute: int = Field(default=60, ge=1)
    org_rate_limit_api_per_minute: int = Field(default=3000, ge=1)
    org_chat_messages_per_day: int = Field(default=0, ge=0)  # 0 = unlimited
    # Number of reverse proxies in front of the API. X-Forwarded-For is only
    # trusted for that many hops; 0 means use the socket peer address, so a
    # client cannot evade IP rate limits by sending its own header.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    # Chat history:
    conversation_auto_title: bool = True
    # Soft-deleted conversations can be restored for this long, then purged.
    conversation_delete_retention_days: int = Field(default=30, ge=0, le=3650)
    # Prior user/assistant turns sent to the model with each question.
    conversation_prompt_turns: int = Field(default=2, ge=0, le=20)

    # Enhanced Retrieval:
    max_conversation_history: int = Field(default=2)
    document_scope_message_threshold: int = Field(default=5)

    # Logging:
    log_level: str = "INFO"
    log_file: str = "./logs/novera.log"
    log_rotation: str = "10 MB"
    log_retention: str = "30 days"

    # CORS:
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
    )
    cors_allow_credentials: bool = True

    @property
    def cors_origins_list(self) -> List[str]:
        """
        Parse CORS origins string into a deduplicated list.
        Strips trailing slashes to prevent silent mismatches.
        In development, localhost variants are auto-added.
        """
        if isinstance(self.cors_origins, str):
            cleaned = self.cors_origins.strip().strip('[]"\'')
            origins = [
                o.strip().strip('"\'').rstrip("/")
                for o in cleaned.split(",")
                if o.strip()
            ]
        else:
            origins = [o.rstrip("/") for o in self.cors_origins]

        if self.environment in ("development", "local", "docker"):
            local = [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ]
            origins = list(dict.fromkeys(origins + local))  # dedup, preserve order

        return origins

    # Validators:

    @field_validator(
        "gemini_api_key", "cohere_api_key", "openai_api_key", "anthropic_api_key",
        mode="before",
    )
    @classmethod
    def validate_api_keys(cls, v: Optional[str], info) -> Optional[str]:
        """Treat empty string as None; validate key length when provided."""
        if not v:
            return None
        if len(v) < 10:
            raise ValueError(f"{info.field_name} is too short — check your API key")
        return v

    @field_validator(
        "llm_provider", "llm_model", "llm_api_key", "llm_base_url", "llm_utility_model",
        "embedding_provider", "embedding_model", "embedding_api_key", "embedding_base_url",
        "rerank_provider", "rerank_model", "rerank_api_key", "rerank_base_url",
        "eval_judge_provider", "eval_judge_model", "ai_secrets_key",
        "gemini_chat_model", "gemini_embedding_model", "cohere_rerank_model",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, v):
        return v.strip() if isinstance(v, str) and v.strip() else None

    def credential_for(self, provider: Optional[str]) -> Optional[str]:
        """Platform API key for a provider, if one is configured."""
        from app.services.ai.catalog import ALIASES

        provider = ALIASES.get(provider or "", provider or "")
        return {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
            "cohere": self.cohere_api_key,
        }.get(provider)

    @model_validator(mode="after")
    def resolve_legacy_ai_settings(self) -> "Settings":
        """Map the pre-multi-provider GEMINI_*/COHERE_* settings onto the generic ones."""
        if not self.llm_provider and self.gemini_api_key and self.gemini_chat_model:
            self.llm_provider = "gemini"
            self.llm_model = self.llm_model or self.gemini_chat_model
        if not self.embedding_provider and self.gemini_api_key and self.gemini_embedding_model:
            self.embedding_provider = "gemini"
            self.embedding_model = self.embedding_model or self.gemini_embedding_model
            if self.gemini_embedding_dimensions:
                self.embedding_dimensions = self.gemini_embedding_dimensions
        if not self.rerank_provider and self.cohere_api_key and self.cohere_rerank_model:
            self.rerank_provider = "cohere"
            self.rerank_model = self.rerank_model or self.cohere_rerank_model
        if self.llm_provider:
            self.llm_api_key = self.llm_api_key or self.credential_for(self.llm_provider)
        if self.embedding_provider:
            self.embedding_api_key = (
                self.embedding_api_key or self.credential_for(self.embedding_provider)
            )
        if self.rerank_provider and self.rerank_provider != "none":
            self.rerank_api_key = self.rerank_api_key or self.credential_for(self.rerank_provider)
        return self

    @field_validator("secret_key", mode="before")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    @model_validator(mode="after")
    def validate_production_integrations(self) -> "Settings":
        """Fail startup rather than discovering missing critical integrations per request."""
        if self.environment.lower() in {"production", "prod"}:
            if not (self.llm_provider and self.llm_model):
                raise ValueError("LLM_PROVIDER and LLM_MODEL are required in production")
            if not (self.embedding_provider and self.embedding_model):
                raise ValueError(
                    "EMBEDDING_PROVIDER and EMBEDDING_MODEL are required in production"
                )
            if not self.rerank_provider:
                raise ValueError(
                    "RERANK_PROVIDER is required in production (set it to 'none' to "
                    "disable reranking deliberately) so reranking never silently degrades"
                )
        return self


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton — reads .env once at startup."""
    return Settings()


settings = get_settings()

__all__ = ["settings", "get_settings", "Settings"]
