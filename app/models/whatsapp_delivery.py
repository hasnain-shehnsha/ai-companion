import uuid

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func

from app.core.database import Base


class WhatsAppTemplateDelivery(Base):
    __tablename__ = "whatsapp_template_deliveries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    to_number = Column(String, nullable=False, index=True)
    template_name = Column(String, nullable=False)
    language = Column(String, nullable=False)
    parameters = Column(JSON, nullable=True)
    provider_response = Column(JSON, nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
