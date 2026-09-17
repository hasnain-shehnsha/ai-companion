import datetime
import uuid

import pytest

from app.core.security import get_password_hash
from app.models.chat import ChatSession
from app.models.usage import UsageRecord
from app.models.user import User, UserTier


@pytest.fixture
async def free_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Test",
        last_name="User",
        email="free@example.com",
        hashed_password=get_password_hash("password123"),
        whatsapp_number="+923001234567",
        tier=UserTier.FREE,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def paid_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Test",
        last_name="User",
        email="paid@example.com",
        hashed_password=get_password_hash("password123"),
        whatsapp_number="+923001234568",
        tier=UserTier.PAID,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def get_token(async_client, email):
    response = await async_client.post(
        "/users/login",
        json={"email": email, "password": "password123"},
    )
    return response.json()["access_token"]


async def test_free_chat_quota(async_client, db_session, free_user, mocker):
    token = await get_token(async_client, free_user.email)

    from app.core.exceptions import QuotaExceededException

    mocker.patch(
        "app.services.ai_service.generate_chat_completion",
        side_effect=QuotaExceededException(
            "You've reached your daily limit of 50 messages."
        ),
    )

    # Now attempt chat
    response = await async_client.post(
        "/chat/",
        json={"message": "What is my nickname?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "daily limit of 50 messages" in response.json()["response"]


async def test_anonymous_free_chat(async_client, mocker):
    mocker.patch(
        "app.services.ai_service.analyze_intent",
        return_value=type(
            "Intent",
            (),
            {"intent": "CHAT", "datetime_iso": None, "reminder_text": None},
        )(),
    )

    response = await async_client.post("/chat/", json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json()["response"] == "Mock LLM response"


async def test_paid_chat_quota(async_client, db_session, paid_user):
    token = await get_token(async_client, paid_user.email)

    # Fill quota to 50
    now = datetime.datetime.now(datetime.UTC)
    for _ in range(50):
        db_session.add(
            UsageRecord(
                id=str(uuid.uuid4()),
                user_id=paid_user.id,
                model="test",
                request_type="chat",
                channel="web",
                created_at=now,
            )
        )
    await db_session.commit()

    # Attempt chat, should pass because paid limit is 500
    response = await async_client.post(
        "/chat/",
        json={"message": "Hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "Mock LLM response" in response.json()["response"]


async def test_session_ownership(async_client, db_session, free_user, paid_user):
    token = await get_token(async_client, free_user.email)

    session = ChatSession(
        id=str(uuid.uuid4()), user_id=paid_user.id, title="Test Session"
    )
    db_session.add(session)
    await db_session.commit()

    # Free user attempts to use paid user's session
    response = await async_client.post(
        "/chat/",
        json={"message": "Hello", "session_id": session.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"


async def test_message_persistence_and_session_creation(
    async_client, paid_user, db_session
):
    token = await get_token(async_client, paid_user.email)

    # First chat, should create a session implicitly?
    # Wait, the endpoint code says if chat_request.session_id is not provided, it doesn't create one in the POST /chat/
    # Let's create a session first via POST /chat/sessions
    session_response = await async_client.post(
        "/chat/sessions",
        json={"title": "My new session"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = session_response.json()["id"]

    response = await async_client.post(
        "/chat/",
        json={"message": "Hello AI", "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    # Verify in DB
    # The message should be persisted inside handle_chat?
    # handle_chat relies on extract_atomic_facts etc.
    # Let's verify history endpoint returns it
    history_response = await async_client.get(
        f"/chat/sessions/{session_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    messages = history_response.json()
    assert [message["role"] for message in messages] == ["user", "assistant"]


async def test_llm_failure(async_client, free_user, mocker):
    token = await get_token(async_client, free_user.email)

    # Mock LLM to throw an exception
    mocker.patch(
        "app.services.ai_service.generate_chat_completion",
        side_effect=Exception("API Down"),
    )

    response = await async_client.post(
        "/chat/",
        json={"message": "Hello"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # The ai_service doesn't catch generate_chat_completion failure inside handle_chat unless it's handled
    # Wait, handle_chat has no try/except around generate_chat_completion, it bubbles up to FastAPI 500,
    # or generate_chat_completion catches it internally. We updated generate_chat_completion to return ""
    assert response.status_code == 500


async def test_qdrant_failure(async_client, paid_user, mocker):
    token = await get_token(async_client, paid_user.email)
    mocker.patch(
        "app.services.ai_service.analyze_intent",
        return_value=type(
            "Intent",
            (),
            {
                "intent": "CHAT",
                "datetime_iso": None,
                "reminder_text": None,
                "search_query": "nickname",
                "is_general_question": False,
            },
        )(),
    )

    # Mock Qdrant retrieval failure
    mocker.patch(
        "app.services.ai_service.retrieve_relevant_facts",
        side_effect=Exception("Qdrant Down"),
    )

    response = await async_client.post(
        "/chat/",
        json={"message": "What is my nickname?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
