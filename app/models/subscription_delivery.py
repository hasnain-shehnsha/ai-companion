import enum
import uuid

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.database import Base


class DeliveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"


class SubscriptionDelivery(Base):
    __tablename__ = "subscription_deliveries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id = Column(
        String, ForeignKey("daily_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    delivery_date = Column(Date, nullable=False, index=True)
    status = Column(
        Enum(DeliveryStatus), default=DeliveryStatus.PENDING, nullable=False
    )

    attempt_count = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "delivery_date", name="uq_subscription_delivery_date"
        ),
    )
