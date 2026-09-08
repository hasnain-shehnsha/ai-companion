from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    message: str
    chat_history: Optional[list[dict]] = None


class ChatResponse(BaseModel):
    response: str
    extracted_facts: Optional[list[str]] = None
    memory_error: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime


class UserStateResponse(BaseModel):
    is_onboarding_completed: bool
    messages: list[MessageResponse]
