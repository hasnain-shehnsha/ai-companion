from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import users, chat, whatsapp
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI Companion API serving Web and WhatsApp channels.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(whatsapp.router, prefix="/whatsapp", tags=["WhatsApp"])

@app.get("/")
async def root():
    return {"message": "Welcome to the AI Companion API"}
