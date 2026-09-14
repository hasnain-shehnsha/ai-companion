from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(
        String, ForeignKey("users.id"), nullable=True
    )  # Nullable for anonymous users
    model = Column(String, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    request_type = Column(
        String, nullable=False
    )  # e.g., "chat", "fact_extraction", "title_generation", "scheduler"
    channel = Column(String, nullable=False)  # e.g., "web", "whatsapp", "background"
    estimated_cost = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
