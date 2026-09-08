from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    UserStateResponse,
    ChatSessionResponse,
    MessageResponse,
)
from app.services.user_service import get_user
from app.services.ai_service import handle_chat
from app.services.llm_service import generate_session_title
from app.crud.chat_crud import (
    get_session,
    update_session_title,
    get_user_sessions,
    create_session,
    get_session_messages,
)
from app.core.database import get_db

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat_with_companion(
    chat_request: ChatRequest, db: AsyncSession = Depends(get_db)
):
    user = None
    session = None
    if chat_request.user_id:
        user = await get_user(db, chat_request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if chat_request.session_id:
            session = await get_session(db, chat_request.session_id, user.id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            if session.title == "New Conversation":
                new_title = await generate_session_title(chat_request.message)
                await update_session_title(db, session, new_title)

    response_data = await handle_chat(
        db,
        user,
        chat_request.message,
        chat_request.chat_history,
        session_id=session.id if session else None,
    )

    return ChatResponse(
        response=response_data["response"],
        extracted_facts=response_data.get("extracted_facts"),
        memory_error=response_data.get("memory_error"),
    )


@router.get("/user_state/{user_id}", response_model=UserStateResponse)
async def get_user_state(user_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserStateResponse(
        is_onboarding_completed=user.is_onboarding_completed, messages=[]
    )


@router.get("/sessions/{user_id}", response_model=list[ChatSessionResponse])
async def get_user_chat_sessions(user_id: str, db: AsyncSession = Depends(get_db)):
    sessions = await get_user_sessions(db, user_id)
    return [
        {"id": s.id, "title": s.title, "created_at": s.created_at} for s in sessions
    ]


@router.post("/sessions/{user_id}", response_model=ChatSessionResponse)
async def create_new_chat_session(user_id: str, db: AsyncSession = Depends(get_db)):
    new_session = await create_session(db, user_id)
    return {
        "id": new_session.id,
        "title": new_session.title,
        "created_at": new_session.created_at,
    }


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages_for_session(session_id: str, db: AsyncSession = Depends(get_db)):
    history = await get_session_messages(db, session_id)
    return [{"id": msg.id, "role": msg.role, "content": msg.content} for msg in history]
