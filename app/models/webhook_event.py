from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    # We store the Meta message ID here. It's typically a wamid.XXX string
    id = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
