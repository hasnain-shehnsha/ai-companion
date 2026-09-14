import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "AI Companion Backend"

    # Required across all environments
    DATABASE_URL: str
    GROQ_API_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )


class DevelopmentSettings(Settings):
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    WHATSAPP_TOKEN: str = "dev_whatsapp_token"
    WHATSAPP_PHONE_NUMBER_ID: str = "dev_phone_id"
    WHATSAPP_VERIFY_TOKEN: str = "dev_verify_token"
    META_APP_SECRET: str | None = None

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    REDIS_URL: str = "redis://localhost:6379/0"
    RESEND_API_KEY: str = "dev_resend_api_key"

    SECRET_KEY: str = "dev-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7


class TestSettings(Settings):
    ENVIRONMENT: str = "test"
    ALLOWED_ORIGINS: str = "*"

    WHATSAPP_TOKEN: str = "test_whatsapp_token"
    WHATSAPP_PHONE_NUMBER_ID: str = "test_phone_id"
    WHATSAPP_VERIFY_TOKEN: str = "test_verify_token"
    META_APP_SECRET: str | None = None

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    REDIS_URL: str = "redis://localhost:6379/1"
    RESEND_API_KEY: str = "test_resend_api_key"

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

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    REDIS_URL: str
    RESEND_API_KEY: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7


class ProductionSettings(Settings):
    ENVIRONMENT: str = "production"
    ALLOWED_ORIGINS: str

    WHATSAPP_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_VERIFY_TOKEN: str
    META_APP_SECRET: str | None = None

    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None

    REDIS_URL: str
    RESEND_API_KEY: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7


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
