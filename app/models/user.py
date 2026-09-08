import enum
from sqlalchemy import Column, String, Enum, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base
import uuid


class UserTier(str, enum.Enum):
    FREE = "FREE"
    PAID = "PAID"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    whatsapp_number = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    tier = Column(Enum(UserTier), default=UserTier.FREE, nullable=False)
    chat_summary = Column(String, default="", nullable=False)
    is_onboarding_completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
