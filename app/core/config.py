from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Companion Backend"

    DATABASE_URL: str

    GROQ_API_KEY: str

    WHATSAPP_TOKEN: str = "your_whatsapp_token_here"
    WHATSAPP_PHONE_NUMBER_ID: str = "your_phone_id_here"
    WHATSAPP_VERIFY_TOKEN: str = "companion_verify_token"
    META_APP_SECRET: str | None = None

    QDRANT_URL: str = "https://your-qdrant-cluster-url.qdrant.tech"
    QDRANT_API_KEY: str = ""

    REDIS_URL: str = "redis://localhost:6379/0"

    RESEND_API_KEY: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
