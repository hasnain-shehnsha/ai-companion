import enum

from sqlalchemy import Column, DateTime, Enum, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class WebhookStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    # We store the Meta message ID here. It's typically a wamid.XXX string
    id = Column(String, primary_key=True)
    wa_id = Column(String, nullable=False)
    text = Column(String, nullable=False)
    status = Column(Enum(WebhookStatus), default=WebhookStatus.RECEIVED, nullable=False)

    attempt_count = Column(Integer, default=0, server_default="0", nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
