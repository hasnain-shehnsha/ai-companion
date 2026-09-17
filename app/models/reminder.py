import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class ReminderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    PARTIALLY_SENT = "PARTIALLY_SENT"
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
    email_status = Column(String, nullable=True)
    whatsapp_status = Column(String, nullable=True)

    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, default=0, server_default="0", nullable=False)
    failure_reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
