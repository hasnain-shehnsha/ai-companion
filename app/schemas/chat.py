from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000, strip_whitespace=True)


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=2000, strip_whitespace=True)
    chat_history: list[ChatHistoryItem] | None = Field(None, max_length=20)


class ChatResponse(BaseModel):
    response: str
    extracted_facts: list[str] | None = None
    memory_error: str | None = None
    user_message_id: str | None = None
    ai_message_id: str | None = None


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
