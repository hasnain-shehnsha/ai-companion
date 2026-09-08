from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from app.models.user import UserTier


class UserBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    whatsapp_number: str
    tier: UserTier = UserTier.FREE


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
