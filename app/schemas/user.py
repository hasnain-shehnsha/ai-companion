from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
import phonenumbers
from app.models.user import UserTier


class UserBase(BaseModel):
    first_name: str = Field(..., min_length=2, max_length=50, strip_whitespace=True)
    last_name: str = Field(..., min_length=2, max_length=50, strip_whitespace=True)
    email: EmailStr
    whatsapp_number: str = Field(..., min_length=10, max_length=20)
    tier: UserTier = UserTier.FREE

    @field_validator("whatsapp_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
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


class UserLogin(BaseModel):
    email: EmailStr
    password: str


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
