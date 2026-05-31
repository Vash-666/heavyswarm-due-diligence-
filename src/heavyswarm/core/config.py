"""Configuration management for HeavySwarm."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # =========================================================================
    # API Configuration
    # =========================================================================
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_workers: int = Field(default=4, alias="API_WORKERS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production"
    
    # =========================================================================
    # Security
    # =========================================================================
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # =========================================================================
    # Database Configuration
    # =========================================================================
    database_url: str = Field(
        default="postgresql+asyncpg://diligence:diligence@localhost:5432/diligence",
        alias="DATABASE_URL",
    )
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="diligence", alias="DB_NAME")
    db_user: str = Field(default="diligence", alias="DB_USER")
    db_password: str = Field(default="diligence", alias="DB_PASSWORD")
    
    # =========================================================================
    # Cache Configuration
    # =========================================================================
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")
    
    cache_ttl_short: int = Field(default=300, alias="CACHE_TTL_SHORT")  # 5 minutes
    cache_ttl_medium: int = Field(default=3600, alias="CACHE_TTL_MEDIUM")  # 1 hour
    cache_ttl_long: int = Field(default=86400, alias="CACHE_TTL_LONG")  # 24 hours
    
    # =========================================================================
    # LLM Configuration
    # =========================================================================
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    xai_api_key: Optional[str] = Field(default=None, alias="XAI_API_KEY")
    
    default_model: str = Field(default="claude-3-5-sonnet-20241022", alias="DEFAULT_MODEL")
    fallback_model: str = Field(default="gpt-4o", alias="FALLBACK_MODEL")
    max_concurrent_llm_calls: int = Field(default=10, alias="MAX_CONCURRENT_LLM_CALLS")
    llm_timeout_seconds: int = Field(default=60, alias="LLM_TIMEOUT_SECONDS")
    
    # =========================================================================
    # External Data Sources
    # =========================================================================
    alpha_vantage_api_key: Optional[str] = Field(default=None, alias="ALPHA_VANTAGE_API_KEY")
    bloomberg_api_key: Optional[str] = Field(default=None, alias="BLOOMBERG_API_KEY")
    bloomberg_api_url: str = Field(
        default="https://api.bloomberg.com/v1", alias="BLOOMBERG_API_URL"
    )
    sec_user_agent: str = Field(
        default="HeavySwarm Engine contact@heavyswarm.io", alias="SEC_USER_AGENT"
    )
    newsapi_key: Optional[str] = Field(default=None, alias="NEWSAPI_KEY")
    
    # =========================================================================
    # Trading System Integration
    # =========================================================================
    trading_webhook_secret: Optional[str] = Field(default=None, alias="TRADING_WEBHOOK_SECRET")
    trading_webhook_url: Optional[str] = Field(default=None, alias="TRADING_WEBHOOK_URL")
    
    # =========================================================================
    # Quality & Performance
    # =========================================================================
    confidence_threshold: float = Field(default=0.85, alias="CONFIDENCE_THRESHOLD")
    risk_score_threshold: float = Field(default=70.0, alias="RISK_SCORE_THRESHOLD")
    max_position_size_pct: float = Field(default=0.05, alias="MAX_POSITION_SIZE_PCT")
    quality_gate_enabled: bool = Field(default=True, alias="QUALITY_GATE_ENABLED")
    
    max_concurrent_diligences: int = Field(default=10, alias="MAX_CONCURRENT_DILIGENCES")
    default_diligence_timeout_seconds: int = Field(
        default=300, alias="DEFAULT_DILIGENCE_TIMEOUT_SECONDS"
    )
    
    # =========================================================================
    # Monitoring
    # =========================================================================
    enable_metrics: bool = Field(default=True, alias="ENABLE_METRICS")
    metrics_port: int = Field(default=9090, alias="METRICS_PORT")
    tracing_enabled: bool = Field(default=True, alias="TRACING_ENABLED")
    sentry_dsn: Optional[str] = Field(default=None, alias="SENTRY_DSN")
    
    # =========================================================================
    # Feature Flags
    # =========================================================================
    enable_quality_guardian: bool = Field(default=True, alias="ENABLE_QUALITY_GUARDIAN")
    enable_parallel_execution: bool = Field(default=True, alias="ENABLE_PARALLEL_EXECUTION")
    enable_circuit_breaker: bool = Field(default=True, alias="ENABLE_CIRCUIT_BREAKER")
    enable_cache: bool = Field(default=True, alias="ENABLE_CACHE")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance.
    
    Returns:
        Settings: Application settings
    """
    return Settings()


# Global settings instance
settings = get_settings()
