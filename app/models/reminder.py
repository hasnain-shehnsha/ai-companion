import enum
from sqlalchemy import Column, String, Enum, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base
import uuid


class ReminderStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message = Column(String, nullable=False)
    remind_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(
        Enum(ReminderStatus), default=ReminderStatus.PENDING, nullable=False
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
