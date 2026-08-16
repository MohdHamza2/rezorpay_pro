from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"  # "development", "staging", "production"
    APP_NAME: str = "InvoiceSaaS"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/invoicesaas"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Rate Limiting
    RATE_LIMIT_AUTH: str = "5/minute"

    # Redis (for future rate limiting backend + task queues)
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
