from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import phonenumbers
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import UserTier


class UserBase(BaseModel):
    first_name: str = Field(..., min_length=2, max_length=50, strip_whitespace=True)
    last_name: str = Field(..., min_length=2, max_length=50, strip_whitespace=True)
    email: EmailStr
    whatsapp_number: str = Field(..., min_length=10, max_length=20)
    tier: UserTier = UserTier.FREE
    timezone: str = Field(default="UTC", description="IANA timezone string")
    email_verified: bool = False
    whatsapp_verified: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
            return v
        except ZoneInfoNotFoundError:
            raise ValueError(f"Invalid timezone: {v}")

    @field_validator("whatsapp_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if v and not v.startswith("+") and v.isdigit():
            v = "+" + v

        try:
            parsed = phonenumbers.parse(v)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("Invalid phone number format")
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
        except phonenumbers.phonenumberutil.NumberParseException:
            raise ValueError("Invalid phone number format")


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    first_name: str | None = Field(
        None, min_length=2, max_length=50, strip_whitespace=True
    )
    last_name: str | None = Field(
        None, min_length=2, max_length=50, strip_whitespace=True
    )
    timezone: str | None = Field(None, description="IANA timezone string")
    whatsapp_number: str | None = Field(None, min_length=10, max_length=20)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                ZoneInfo(v)
            except ZoneInfoNotFoundError:
                raise ValueError(f"Invalid timezone: {v}")
        return v

    @field_validator("whatsapp_number")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if v and not v.startswith("+") and v.isdigit():
            v = "+" + v

        try:
            parsed = phonenumbers.parse(v)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("Invalid phone number format")
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
        except phonenumbers.phonenumberutil.NumberParseException:
            raise ValueError("Invalid phone number format")


class VerificationSendRequest(BaseModel):
    channel: str  # 'EMAIL' or 'WHATSAPP'


class VerificationVerifyRequest(BaseModel):
    channel: str
    code: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
