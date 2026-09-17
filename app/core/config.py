import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "AI Companion Backend"

    # Required across all environments
    DATABASE_URL: str
    GROQ_API_KEY: str
    META_GRAPH_API_VERSION: str = "v20.0"
    MEMORY_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )


class DevelopmentSettings(Settings):
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    WHATSAPP_TOKEN: str = "dev_whatsapp_token"
    WHATSAPP_PHONE_NUMBER_ID: str = "dev_phone_id"
    WHATSAPP_VERIFY_TOKEN: str = "dev_verify_token"
    META_APP_SECRET: str | None = None
    WHATSAPP_REMINDER_TEMPLATE_NAME: str = "utility_reminder"
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en_US"

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    REDIS_URL: str = "redis://localhost:6379/0"
    RESEND_API_KEY: str = "dev_resend_api_key"
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"
    RESEND_FROM_NAME: str = "AI Companion"

    SECRET_KEY: str = "dev-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7


class TestSettings(Settings):
    ENVIRONMENT: str = "test"
    ALLOWED_ORIGINS: str = "*"

    # Use TEST_DATABASE_URL if available, else default to an in-memory SQLite for tests to prevent touching production DB
    DATABASE_URL: str = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    WHATSAPP_TOKEN: str = "test_whatsapp_token"
    WHATSAPP_PHONE_NUMBER_ID: str = "test_phone_id"
    WHATSAPP_VERIFY_TOKEN: str = "test_verify_token"
    META_APP_SECRET: str | None = None
    WHATSAPP_REMINDER_TEMPLATE_NAME: str = "utility_reminder"
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en_US"

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    REDIS_URL: str = "redis://localhost:6379/1"
    RESEND_API_KEY: str = "test_resend_api_key"
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"
    RESEND_FROM_NAME: str = "AI Companion"

    SECRET_KEY: str = "test-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60


class StagingSettings(Settings):
    ENVIRONMENT: str = "staging"
    ALLOWED_ORIGINS: str

    WHATSAPP_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_VERIFY_TOKEN: str
    META_APP_SECRET: str | None = None
    WHATSAPP_REMINDER_TEMPLATE_NAME: str = "utility_reminder"
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en_US"

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    REDIS_URL: str
    RESEND_API_KEY: str
    RESEND_FROM_EMAIL: str
    RESEND_FROM_NAME: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7


class ProductionSettings(Settings):
    ENVIRONMENT: str = "production"
    ALLOWED_ORIGINS: str

    WHATSAPP_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_VERIFY_TOKEN: str
    META_APP_SECRET: str
    WHATSAPP_REMINDER_TEMPLATE_NAME: str = "utility_reminder"
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en_US"

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    REDIS_URL: str
    RESEND_API_KEY: str
    RESEND_FROM_EMAIL: str
    RESEND_FROM_NAME: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    @model_validator(mode="after")
    def check_qdrant_if_memory_enabled(self):
        if self.MEMORY_ENABLED:
            if not self.QDRANT_URL or not self.QDRANT_API_KEY:
                raise ValueError(
                    "QDRANT_URL and QDRANT_API_KEY are required in production when MEMORY_ENABLED is True."
                )
        return self

    @model_validator(mode="after")
    def check_resend_production_identity(self):
        if self.RESEND_FROM_EMAIL.endswith("@resend.dev"):
            raise ValueError(
                "Production environment requires a verified custom domain for RESEND_FROM_EMAIL, not a @resend.dev sandbox address."
            )
        return self


def get_settings():
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env == "production":
        return ProductionSettings()
    elif env == "staging":
        return StagingSettings()
    elif env == "test":
        return TestSettings()
    return DevelopmentSettings()


settings = get_settings()
