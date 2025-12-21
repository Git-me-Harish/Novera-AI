"""
Core configuration module using Pydantic settings management.
Loads environment variables and provides type-safe configuration access.
"""
from typing import List, Optional, Union
from pydantic import Field, field_validator
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
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 3600
    
    # Google Gemini Configuration
    gemini_api_key: str
    gemini_embedding_model: str = "models/text-embedding-004"  
    gemini_embedding_dimensions: int = 1536 
    gemini_chat_model: str = "gemini-2.5-flash" 
    gemini_max_tokens: int = 8192
    
    # Cohere Configuration
    cohere_api_key: str
    cohere_rerank_model: str = "rerank-english-v3.0"
    
    # JWT Authentication
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Email Configuration
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_email: str = Field(default="")
    smtp_from_name: str = Field(default="Novera AI")
    smtp_use_tls: bool = Field(default=True)

    # Password Reset
    password_reset_token_expire_minutes: int = Field(default=15)
    frontend_url: str = Field(default="http://localhost:5173")
    
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
    similarity_threshold: float = Field(default=0.3, env="SIMILARITY_THRESHOLD")
    hybrid_alpha: float = 0.7

    # Dynamic retrieval settings
    enable_dynamic_scope: bool = Field(default=True, env="ENABLE_DYNAMIC_SCOPE")
    min_relevance_for_scoped_search: float = Field(default=0.5, env="MIN_RELEVANCE_SCOPED")
    global_search_top_k: int = Field(default=7, env="GLOBAL_SEARCH_TOP_K")
    scoped_search_top_k: int = Field(default=5, env="SCOPED_SEARCH_TOP_K")
    
    # Generation Configuration
    max_context_tokens: int = 12000
    temperature: float = 0.1
    max_response_tokens: int = 2000
    
    # Guardrails Configuration
    enable_input_guardrails: bool = True
    enable_output_guardrails: bool = True
    hallucination_threshold: float = 0.3
    
    # Query Classification
    enable_llm_classification: bool = Field(default=True, env="ENABLE_LLM_CLASSIFICATION")
    classification_cache_ttl: int = Field(default=3600, env="CLASSIFICATION_CACHE_TTL")

    # Context Management Configuration
    context_timeout_hours: int = Field(default=1, env="CONTEXT_TIMEOUT_HOURS")
    context_max_documents: int = Field(default=5, env="CONTEXT_MAX_DOCUMENTS")
    context_boost_factor: float = Field(default=1.5, env="CONTEXT_BOOST_FACTOR")
    enable_query_reformulation: bool = Field(default=True, env="ENABLE_QUERY_REFORMULATION")
    enable_context_ui: bool = Field(default=True, env="ENABLE_CONTEXT_UI")
    
    # Enhanced Retrieval
    max_conversation_history: int = Field(default=2, env="MAX_CONVERSATION_HISTORY")
    document_scope_message_threshold: int = Field(default=5, env="DOCUMENT_SCOPE_MESSAGE_THRESHOLD")
    
    # Logging Configuration
    log_level: str = "INFO"
    log_file: str = "./logs/mentanova.log"
    log_rotation: str = "10 MB"
    log_retention: str = "30 days"
    
    # CORS Settings
    cors_origins: Union[str, List[str]] = "http://localhost:3000,http://localhost:5173"
    cors_allow_credentials: bool = True
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            v = v.strip('[]"\'')
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @field_validator("gemini_api_key", "cohere_api_key", "secret_key")
    @classmethod
    def validate_secrets(cls, v, info):
        """Ensure critical secrets are not using placeholder values."""
        field_name = info.field_name
        
        if field_name == "secret_key":
            if not v or len(v) < 20:
                raise ValueError(f"{field_name} must be at least 20 characters long")
        
        if field_name in ["gemini_api_key", "cohere_api_key"]:
            if not v or len(v) < 10:
                raise ValueError(f"{field_name} cannot be empty")
        
        return v

@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()

__all__ = ["settings", "get_settings", "Settings"]
