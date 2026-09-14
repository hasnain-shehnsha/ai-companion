from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    UserStateResponse,
    ChatSessionResponse,
    MessageResponse,
)
from app.services.ai_service import handle_chat
from app.services.llm_service import generate_session_title
from app.crud.chat_crud import (
    get_session,
    update_session_title,
    get_user_sessions,
    create_session,
    get_session_messages,
    delete_chat_session,
    delete_chat_message,
)
from app.services.memory_service import delete_facts_by_message, delete_facts_by_session
from app.core.database import get_db
from app.api.deps import get_current_user, get_optional_current_user
from app.models.user import User
from app.core.limiter import limiter

router = APIRouter()


@router.post("/", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_with_companion(
    request: Request,
    chat_request: ChatRequest,
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = None
    user = current_user
    if chat_request.session_id:
        if not user:
            raise HTTPException(
                status_code=401, detail="Login required to use chat sessions"
            )
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
        (
            [item.model_dump() for item in chat_request.chat_history]
            if chat_request.chat_history
            else None
        ),
        session_id=session.id if session else None,
        channel="web",
    )

    return ChatResponse(
        response=response_data["response"],
        extracted_facts=response_data.get("extracted_facts"),
        memory_error=response_data.get("memory_error"),
        user_message_id=response_data.get("user_message_id"),
        ai_message_id=response_data.get("ai_message_id"),
    )


@router.get("/user_state", response_model=UserStateResponse)
async def get_user_state(current_user: User = Depends(get_current_user)):
    return UserStateResponse(
        is_onboarding_completed=current_user.is_onboarding_completed
    )


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def get_user_chat_sessions(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    sessions = await get_user_sessions(db, current_user.id)
    return [
        {"id": s.id, "title": s.title, "created_at": s.created_at} for s in sessions
    ]


@router.post("/sessions", response_model=ChatSessionResponse)
async def create_new_chat_session(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    new_session = await create_session(db, current_user.id)
    return {
        "id": new_session.id,
        "title": new_session.title,
        "created_at": new_session.created_at,
    }


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages_for_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Ensure session belongs to user
    session = await get_session(db, session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    history = await get_session_messages(db, session_id)
    return [{"id": msg.id, "role": msg.role, "content": msg.content} for msg in history]


@router.delete("/sessions/{session_id}")
async def delete_session_endpoint(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    success = await delete_chat_session(db, session_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=404, detail="Session not found or access denied"
        )

    # Also delete facts tied to this session in Qdrant
    background_tasks.add_task(delete_facts_by_session, current_user.id, session_id)

    return {"message": "Session deleted successfully"}


@router.delete("/messages/{message_id}")
async def delete_message_endpoint(
    message_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    success = await delete_chat_message(db, message_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=404, detail="Message not found or access denied"
        )

    # Also delete facts tied to this message in Qdrant
    background_tasks.add_task(delete_facts_by_message, current_user.id, message_id)

    return {"message": "Message deleted successfully"}
