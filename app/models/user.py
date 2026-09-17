import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, String
from sqlalchemy.sql import func

from app.core.database import Base


class UserTier(str, enum.Enum):
    FREE = "FREE"
    PAID = "PAID"


class OnboardingState(str, enum.Enum):
    WELCOME = "WELCOME"
    LOCATION = "LOCATION"
    OCCUPATION = "OCCUPATION"
    INTERESTS = "INTERESTS"
    COMPLETE = "COMPLETE"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    whatsapp_number = Column(String, unique=True, index=True, nullable=False)

    __table_args__ = (Index("ix_users_email_lower", func.lower(email), unique=True),)
    hashed_password = Column(String, nullable=False)
    tier = Column(Enum(UserTier), default=UserTier.FREE, nullable=False)
    timezone = Column(String, default="UTC", nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    whatsapp_verified = Column(Boolean, default=False, nullable=False)
    is_onboarding_completed = Column(Boolean, default=False, nullable=False)
    onboarding_state = Column(
        Enum(OnboardingState), default=OnboardingState.WELCOME, nullable=False
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DataResetJobStatus(str, enum.Enum):
    PENDING_DELETION = "PENDING_DELETION"
    DELETED = "DELETED"
    FAILED = "FAILED"


class DataResetJob(Base):
    __tablename__ = "data_reset_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True, nullable=False)
    status = Column(
        Enum(DataResetJobStatus),
        default=DataResetJobStatus.PENDING_DELETION,
        nullable=False,
    )
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
