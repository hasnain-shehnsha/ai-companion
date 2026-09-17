import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import create_access_token
from app.models.usage import UsageRecord
from app.models.user import OnboardingState, User
from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserLoginResponse,
    UserResponse,
    UserUpdate,
)
from app.services.user_service import authenticate_user, create_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register_user(
    request: Request, user_in: UserCreate, db: AsyncSession = Depends(get_db)
):
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


@router.post("/login", response_model=UserLoginResponse)
@limiter.limit("10/minute")
async def login_user(
    request: Request, user_in: UserLogin, db: AsyncSession = Depends(get_db)
):
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
    db: AsyncSession = Depends(get_db),
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


@router.post("/me/reset", status_code=status.HTTP_202_ACCEPTED)
async def reset_user_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Triggers a durable task to wipe all chat messages, sessions, reminders,
    daily subscriptions, and long-term memory facts for the user.
    """
    from app.models.user import DataResetJob, DataResetJobStatus
    from app.tasks.memory_tasks import process_data_reset_job

    # 1. Create a tracking job
    job = DataResetJob(
        user_id=current_user.id, status=DataResetJobStatus.PENDING_DELETION
    )
    db.add(job)

    # 2. Reset onboarding state immediately
    current_user.is_onboarding_completed = False
    current_user.onboarding_state = OnboardingState.WELCOME
    await db.commit()

    # 3. Enqueue the durable Celery task
    process_data_reset_job.delay(job.id)

    return {"message": "reset started", "job_id": job.id}


import datetime
import random

import httpx
import resend

from app.models.verification import VerificationChannel, VerificationCode
from app.schemas.user import VerificationSendRequest, VerificationVerifyRequest
from app.services.whatsapp_service import send_whatsapp_message


@router.post("/me/verify/send", status_code=status.HTTP_200_OK)
async def send_verification_code(
    req: VerificationSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    channel = (
        VerificationChannel.EMAIL
        if req.channel.upper() == "EMAIL"
        else VerificationChannel.WHATSAPP
    )

    # Generate 6 digit code
    code = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=15)

    # Store code
    vc = VerificationCode(
        user_id=current_user.id, channel=channel, code=code, expires_at=expires_at
    )
    db.add(vc)
    await db.commit()

    # Send code
    if channel == VerificationChannel.EMAIL:
        from app.core.config import settings

        resend.api_key = settings.RESEND_API_KEY
        try:
            params = {
                "from": f"{settings.RESEND_FROM_NAME} <{settings.RESEND_FROM_EMAIL}>",
                "to": [current_user.email],
                "subject": "Your Verification Code",
                "html": f"<p>Your verification code is: <strong>{code}</strong></p><p>It will expire in 15 minutes.</p>",
            }
            resend.Emails.send(params)
        except Exception as e:
            err_msg = str(e)
            if "You can only send testing emails to your own email address" in err_msg:
                logger.warning(
                    f"Resend testing mode restriction. MOCKING EMAIL SEND. The code is: {code}"
                )
            else:
                raise

        # Always log the code in the terminal during development for easy testing
        logger.info(f"📧 VERIFICATION CODE FOR {current_user.email}: {code}")
    elif channel == VerificationChannel.WHATSAPP:
        if not current_user.whatsapp_number:
            raise HTTPException(status_code=400, detail="No WhatsApp number configured")
        try:
            wa_number = current_user.whatsapp_number.replace("+", "")
            wa_message = f"Your verification code for AI Companion is: *{code}*. It will expire in 15 minutes."
            await send_whatsapp_message(wa_number, wa_message)
        except httpx.HTTPStatusError as e:
            err_text = e.response.text
            logger.error(f"WhatsApp API Error (verify send): {err_text}")
            if "messaging window" in err_text.lower() or e.response.status_code == 400:
                raise HTTPException(
                    status_code=400,
                    detail="Please send a message to our WhatsApp bot first to open a secure connection, then request the code again.",
                )
            raise HTTPException(
                status_code=500, detail="Failed to send WhatsApp message"
            )

        # Always log the code in the terminal during development for easy testing
        logger.info(f"📱 VERIFICATION CODE FOR {current_user.whatsapp_number}: {code}")

    return {"message": f"Verification code sent to {channel.value}"}


@router.post("/me/verify", status_code=status.HTTP_200_OK)
async def verify_code(
    req: VerificationVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    channel = (
        VerificationChannel.EMAIL
        if req.channel.upper() == "EMAIL"
        else VerificationChannel.WHATSAPP
    )

    result = await db.execute(
        select(VerificationCode)
        .where(
            VerificationCode.user_id == current_user.id,
            VerificationCode.channel == channel,
            VerificationCode.code == req.code,
            VerificationCode.expires_at > datetime.datetime.now(datetime.UTC),
        )
        .order_by(VerificationCode.created_at.desc())
    )
    vc = result.scalars().first()

    if not vc:
        raise HTTPException(
            status_code=400, detail="Invalid or expired verification code"
        )

    if channel == VerificationChannel.EMAIL:
        current_user.email_verified = True
    else:
        current_user.whatsapp_verified = True

    await db.commit()
    return {"message": f"{channel.value} verified successfully"}
