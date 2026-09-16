from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func

from app.schemas.user import UserCreate, UserResponse, UserLogin, UserLoginResponse, UserUpdate
from app.services.user_service import create_user, authenticate_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.api.deps import get_current_user
from app.models.user import User, OnboardingState
from app.models.usage import UsageRecord
from app.crud.chat_crud import reset_user_chat_data
from app.services.memory_service import delete_all_facts_for_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        user = await create_user(db, user_in)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        logger.warning(
            "Registration failed: IntegrityError (Email or Phone already exists)",
            extra={"email": user_in.email},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email or phone number already exists.",
        )
    except Exception as e:
        logger.exception(
            "Unexpected error during user registration", extra={"email": user_in.email}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.post("/login", response_model=UserLoginResponse)
async def login_user(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, user_in.email, user_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    access_token = create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_users_me(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    update_data = user_update.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(current_user, key, value)
        await db.commit()
        await db.refresh(current_user)
    return current_user



@router.get("/me/usage")
async def get_user_usage(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    user_id = current_user.id

    result = await db.execute(
        select(
            UsageRecord.channel,
            func.sum(UsageRecord.input_tokens).label("total_input"),
            func.sum(UsageRecord.output_tokens).label("total_output"),
            func.sum(UsageRecord.estimated_cost).label("total_cost"),
        )
        .where(UsageRecord.user_id == user_id)
        .group_by(UsageRecord.channel)
    )

    usage_data = result.all()

    total_cost = 0.0
    total_tokens = 0
    breakdown = {}

    for row in usage_data:
        channel = row.channel
        input_t = row.total_input or 0
        output_t = row.total_output or 0
        cost = row.total_cost or 0.0

        total_cost += cost
        total_tokens += input_t + output_t

        breakdown[channel] = {
            "input_tokens": input_t,
            "output_tokens": output_t,
            "cost": cost,
        }

    return {
        "total_cost": total_cost,
        "total_tokens": total_tokens,
        "breakdown": breakdown,
    }


@router.post("/me/reset", status_code=status.HTTP_200_OK)
async def reset_user_data(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Wipes all chat messages, sessions, reminders, and daily subscriptions for the user.
    Also clears all long-term memory facts from Qdrant and resets the onboarding state.
    Does NOT delete the user account.
    """
    # 1. Reset chat and scheduling data in PostgreSQL
    await reset_user_chat_data(db, current_user.id)

    # 2. Reset onboarding state
    current_user.is_onboarding_completed = False
    current_user.onboarding_state = OnboardingState.WELCOME
    await db.commit()

    # 3. Clear all facts in Qdrant via a background task
    background_tasks.add_task(delete_all_facts_for_user, current_user.id)

    return {"message": "User data and context have been completely reset."}
