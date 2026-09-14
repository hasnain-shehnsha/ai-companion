from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000, strip_whitespace=True)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=2000, strip_whitespace=True)
    chat_history: Optional[list[ChatHistoryItem]] = Field(None, max_length=20)


class ChatResponse(BaseModel):
    response: str
    extracted_facts: Optional[list[str]] = None
    memory_error: Optional[str] = None
    user_message_id: Optional[str] = None
    ai_message_id: Optional[str] = None


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
