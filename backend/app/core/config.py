"""
Core configuration module using Pydantic settings management.
Loads environment variables and provides type-safe configuration access.
"""
from typing import List, Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings with validation and type safety."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )
    
    # Application Settings
    app_name: str = "Mentanova AI Knowledge Assistant"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    
    # Database Configuration
    database_url: str = Field(..., description="Async PostgreSQL connection URL")
    database_pool_size: int = 20
    database_max_overflow: int = 10
    
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    
    @property
    def sync_database_url(self) -> str:
        """Synchronous database URL for SQLAlchemy operations."""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600
    
    # OpenAI Configuration
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dimensions: int = 1536
    openai_chat_model: str = "gpt-4-turbo-preview"
    openai_max_tokens: int = 128000
    
    # Cohere Configuration
    cohere_api_key: str
    cohere_rerank_model: str = "rerank-english-v3.0"
    
    # JWT Authentication
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Document Processing Configuration
    max_upload_size_mb: int = 50
    allowed_extensions: str = "pdf,docx,doc,txt,xlsx,xls"
    upload_dir: str = "./data/uploads"
    processed_dir: str = "./data/processed"
    
    @property
    def allowed_extensions_list(self) -> List[str]:
        """Parse allowed extensions into a list."""
        return [ext.strip() for ext in self.allowed_extensions.split(",")]
    
    @property
    def max_upload_size_bytes(self) -> int:
        """Convert MB to bytes."""
        return self.max_upload_size_mb * 1024 * 1024
    
    # Chunking Configuration
    chunk_size: int = 800
    chunk_overlap: int = 150
    max_table_tokens: int = 2000
    min_chunk_size: int = 100
    
    # Retrieval Configuration
    retrieval_top_k: int = 20
    rerank_top_k: int = 8
    similarity_threshold: float = 0.7
    hybrid_alpha: float = 0.7
    
    # Generation Configuration
    max_context_tokens: int = 12000
    temperature: float = 0.1
    max_response_tokens: int = 1000
    
    # Guardrails Configuration
    enable_input_guardrails: bool = True
    enable_output_guardrails: bool = True
    hallucination_threshold: float = 0.3
    
    # Logging Configuration
    log_level: str = "INFO"
    log_file: str = "./logs/mentanova.log"
    log_rotation: str = "10 MB"
    log_retention: str = "30 days"
    
    # CORS Settings
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    cors_allow_credentials: bool = True
    
    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("openai_api_key", "cohere_api_key", "secret_key")
    def validate_secrets(cls, v, field):
        """Ensure critical secrets are not using placeholder values."""
        if not v or "your-" in v.lower() or "change-this" in v.lower():
            raise ValueError(f"{field.name} must be set to a valid value")
        return v
    
    class Config:
        """Pydantic config."""
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings singleton.
    Use this function to access settings throughout the application.
    """
    return Settings()


# Global settings instance
settings = get_settings()


# Convenience exports
__all__ = ["settings", "get_settings", "Settings"]