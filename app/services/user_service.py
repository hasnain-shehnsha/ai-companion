import phonenumbers
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:

    try:
        # Parse number (defaulting to PK region if no country code provided)
        parsed_number = phonenumbers.parse(user_in.whatsapp_number, "PK")
        if not phonenumbers.is_valid_number(parsed_number):
            raise ValueError("Invalid WhatsApp number format")
        normalized_number = phonenumbers.format_number(
            parsed_number, phonenumbers.PhoneNumberFormat.E164
        )
    except phonenumbers.NumberParseException:
        raise ValueError("Could not parse WhatsApp number")

    hashed_password = get_password_hash(user_in.password)

    user_data = user_in.model_dump(exclude={"password"})
    user_data["whatsapp_number"] = normalized_number
    user_data["hashed_password"] = hashed_password

    db_user = User(**user_data)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def get_user(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).filter(User.id == user_id))
    return result.scalars().first()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalars().first()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
