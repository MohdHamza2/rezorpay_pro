from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings

# SECRET_KEY is deliberately weak by default so local/dev boot "just works".
# A production boot with this default is refused (see Settings.validate_secret).
DEFAULT_SECRET_KEY = "change-me-in-production"

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
]


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"  # "development", "staging", "production"
    APP_NAME: str = "InvoiceSaaS"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/invoicesaas"

    # JWT
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS (JSON array, e.g. '["https://app.example.com"]')
    CORS_ORIGINS: list[str] = DEFAULT_CORS_ORIGINS

    # Rate Limiting
    RATE_LIMIT_AUTH: str = "5/minute"

    # Redis (for future rate limiting backend + task queues)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Email Engine (Wave 26 — Resend provider). COMMS_DRY_RUN keeps the
    # platform from ever dialing a provider unless deliberately enabled.
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "InvoiceSaaS <noreply@invoicesaas.example>"
    RESEND_WEBHOOK_SECRET: str = ""
    COMMS_DRY_RUN: bool = True

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}

    @model_validator(mode="after")
    def validate_secret(self) -> "Settings":
        if self.ENVIRONMENT == "production" and self.SECRET_KEY == DEFAULT_SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY must be overridden in production. "
                "Refusing to boot with the default 'change-me-in-production'."
            )
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
