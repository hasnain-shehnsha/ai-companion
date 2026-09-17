from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.endpoints import chat, health, users, whatsapp
from app.core.config import settings
from app.core.limiter import limiter
from app.services.memory_service import setup_memory_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize global models and connections off the critical path
    setup_memory_service()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI Companion API serving Web and WhatsApp channels.",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(whatsapp.router, prefix="/whatsapp", tags=["WhatsApp"])
app.include_router(health.router, prefix="/health", tags=["Health"])


@app.get("/")
async def root():
    return {"message": "Welcome to the AI Companion API"}
