from sqlalchemy import Column, String, Boolean, Time, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base
import uuid


class DailySubscription(Base):
    __tablename__ = "daily_subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    topic = Column(String, nullable=False)
    time_of_day = Column(Time(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
