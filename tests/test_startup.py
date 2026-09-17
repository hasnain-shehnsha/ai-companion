import pytest
from pydantic import ValidationError

from app.core.config import ProductionSettings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure no .env or system environment variables interfere with the tests."""
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_PHONE_NUMBER_ID", raising=False)
    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN", raising=False)
    monkeypatch.delenv("META_APP_SECRET", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
    monkeypatch.delenv("RESEND_FROM_NAME", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)


def test_production_startup_fails_missing_config():
    """
    Test that production startup fails when required security/provider configuration is missing.
    """
    incomplete_env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "GROQ_API_KEY": "test_groq_key",
    }

    with pytest.raises(ValidationError) as exc_info:
        ProductionSettings(_env_file=None, **incomplete_env)

    errors = exc_info.value.errors()
    missing_fields = [error["loc"][0] for error in errors if error["type"] == "missing"]

    assert "ALLOWED_ORIGINS" in missing_fields
    assert "WHATSAPP_TOKEN" in missing_fields
    assert "META_APP_SECRET" in missing_fields
    assert "REDIS_URL" in missing_fields
    assert "RESEND_API_KEY" in missing_fields
    assert "SECRET_KEY" in missing_fields


def test_production_startup_fails_invalid_sender_identity():
    """
    Test that production startup fails if the Resend sender identity is a sandbox address.
    """
    complete_env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "GROQ_API_KEY": "test_groq_key",
        "ALLOWED_ORIGINS": "https://example.com",
        "WHATSAPP_TOKEN": "token",
        "WHATSAPP_PHONE_NUMBER_ID": "phone",
        "WHATSAPP_VERIFY_TOKEN": "verify",
        "META_APP_SECRET": "secret",
        "REDIS_URL": "redis://localhost:6379/0",
        "RESEND_API_KEY": "resend",
        "RESEND_FROM_EMAIL": "onboarding@resend.dev",  # Invalid for production
        "RESEND_FROM_NAME": "AI Companion",
        "SECRET_KEY": "secret",
        "MEMORY_ENABLED": "false",
    }

    with pytest.raises(ValidationError) as exc_info:
        ProductionSettings(_env_file=None, **complete_env)

    assert (
        "Production environment requires a verified custom domain for RESEND_FROM_EMAIL"
        in str(exc_info.value)
    )


def test_production_startup_fails_missing_qdrant_when_memory_enabled():
    """
    Test that production startup fails if Qdrant is missing when memory is enabled.
    """
    complete_env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "GROQ_API_KEY": "test_groq_key",
        "ALLOWED_ORIGINS": "https://example.com",
        "WHATSAPP_TOKEN": "token",
        "WHATSAPP_PHONE_NUMBER_ID": "phone",
        "WHATSAPP_VERIFY_TOKEN": "verify",
        "META_APP_SECRET": "secret",
        "REDIS_URL": "redis://localhost:6379/0",
        "RESEND_API_KEY": "resend",
        "RESEND_FROM_EMAIL": "hello@example.com",
        "RESEND_FROM_NAME": "AI Companion",
        "SECRET_KEY": "secret",
        "MEMORY_ENABLED": "true",
        # Missing QDRANT_URL and QDRANT_API_KEY
    }

    with pytest.raises(ValidationError) as exc_info:
        ProductionSettings(_env_file=None, **complete_env)

    assert (
        "QDRANT_URL and QDRANT_API_KEY are required in production when MEMORY_ENABLED is True"
        in str(exc_info.value)
    )


def test_production_startup_succeeds_with_complete_config():
    """
    Test that production startup succeeds when all configuration is present and valid.
    """
    complete_env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "GROQ_API_KEY": "test_groq_key",
        "ALLOWED_ORIGINS": "https://example.com",
        "WHATSAPP_TOKEN": "token",
        "WHATSAPP_PHONE_NUMBER_ID": "phone",
        "WHATSAPP_VERIFY_TOKEN": "verify",
        "META_APP_SECRET": "secret",
        "REDIS_URL": "redis://localhost:6379/0",
        "RESEND_API_KEY": "resend",
        "RESEND_FROM_EMAIL": "hello@example.com",
        "RESEND_FROM_NAME": "AI Companion",
        "SECRET_KEY": "secret",
        "MEMORY_ENABLED": "true",
        "QDRANT_URL": "https://qdrant.example.com",
        "QDRANT_API_KEY": "qdrant_key",
    }

    settings = ProductionSettings(_env_file=None, **complete_env)
    assert settings.ENVIRONMENT == "production"
    assert settings.RESEND_FROM_EMAIL == "hello@example.com"
