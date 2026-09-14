from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import asc, desc, delete
from app.models.chat import Message, ChatSession
from app.models.reminder import Reminder
from app.models.subscription import DailySubscription


async def get_user_sessions(db: AsyncSession, user_id: str):
    """Retrieve all chat sessions for a user, ordered by newest first."""
    result = await db.execute(
        select(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(desc(ChatSession.created_at))
    )
    return result.scalars().all()


async def get_session(db: AsyncSession, session_id: str, user_id: str):
    """Retrieve a specific session by ID and User ID."""
    result = await db.execute(
        select(ChatSession).filter(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def create_session(
    db: AsyncSession, user_id: str, title: str = "New Conversation"
):
    """Create a new chat session."""
    new_session = ChatSession(user_id=user_id, title=title)
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return new_session


async def update_session_title(db: AsyncSession, session: ChatSession, new_title: str):
    """Update the title of a chat session."""
    session.title = new_title
    await db.commit()
    return session


async def get_session_messages(db: AsyncSession, session_id: str):
    """Retrieve all messages for a specific session, ordered chronologically."""
    result = await db.execute(
        select(Message)
        .filter(Message.session_id == session_id)
        .order_by(asc(Message.created_at))
    )
    return result.scalars().all()


async def get_user_messages(
    db: AsyncSession, user_id: str, session_id: str = None, fetch_all: bool = False
):
    """Retrieve messages for a user, optionally filtered by a specific session."""
    query = select(Message).filter(Message.user_id == user_id)
    if not fetch_all:
        if session_id:
            query = query.filter(Message.session_id == session_id)
        else:
            query = query.filter(Message.session_id.is_(None))
    query = query.order_by(asc(Message.created_at))

    result = await db.execute(query)
    return result.scalars().all()


async def save_chat_turn(
    db: AsyncSession, user_id: str, session_id: str, user_message: str, ai_response: str
):
    """Save both the user's message and the AI's response to the database in a single transaction."""
    db_user_msg = Message(
        user_id=user_id, session_id=session_id, role="user", content=user_message
    )
    db_ai_msg = Message(
        user_id=user_id, session_id=session_id, role="assistant", content=ai_response
    )

    db.add(db_user_msg)
    db.add(db_ai_msg)
    await db.commit()

    return db_user_msg, db_ai_msg


async def delete_chat_session(db: AsyncSession, session_id: str, user_id: str) -> bool:
    """Delete a chat session and all its messages (via cascade)."""
    session = await get_session(db, session_id, user_id)
    if not session:
        return False
    await db.delete(session)
    await db.commit()
    return True


async def delete_chat_message(db: AsyncSession, message_id: str, user_id: str) -> bool:
    """Delete a specific message from a session."""
    result = await db.execute(
        select(Message).filter(Message.id == message_id, Message.user_id == user_id)
    )
    message = result.scalar_one_or_none()
    if not message:
        return False
    await db.delete(message)
    await db.commit()
    return True


async def reset_user_chat_data(db: AsyncSession, user_id: str) -> bool:
    """Delete all chat sessions, messages, reminders, and subscriptions for a user."""
    # Delete all messages (including those without sessions like WhatsApp)
    await db.execute(delete(Message).where(Message.user_id == user_id))

    # Delete all sessions
    await db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))

    # Delete all reminders
    await db.execute(delete(Reminder).where(Reminder.user_id == user_id))

    # Delete all daily subscriptions
    await db.execute(
        delete(DailySubscription).where(DailySubscription.user_id == user_id)
    )

    await db.commit()
    return True
