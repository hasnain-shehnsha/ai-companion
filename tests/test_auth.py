import pytest
from app.core.security import get_password_hash
from app.models.user import User
from app.models.chat import Message, ChatSession
import uuid
import datetime


@pytest.fixture
async def test_user(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Test",
        last_name="User",
        email="auth_test@example.com",
        hashed_password=get_password_hash("password123"),
        whatsapp_number="+923001234568",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def test_user_2(db_session):
    user = User(
        id=str(uuid.uuid4()),
        first_name="Test",
        last_name="User",
        email="auth_test2@example.com",
        hashed_password=get_password_hash("password123"),
        whatsapp_number="+923001234569",
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def test_successful_login(async_client, test_user):
    response = await async_client.post(
        "/users/login",
        json={"email": "auth_test@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_invalid_password(async_client, test_user):
    response = await async_client.post(
        "/users/login",
        json={"email": "auth_test@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


async def test_expired_token(async_client, test_user, mocker):
    # Mock ACCESS_TOKEN_EXPIRE_MINUTES to -1 to generate an already expired token
    mocker.patch("app.core.security.settings.ACCESS_TOKEN_EXPIRE_MINUTES", -1)

    login_response = await async_client.post(
        "/users/login",
        json={"email": "auth_test@example.com", "password": "password123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Try to access a protected endpoint
    response = await async_client.get(
        "/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Could not validate credentials"


async def test_accessing_another_users_sessions(
    async_client, db_session, test_user, test_user_2
):
    # User 2 creates a session
    session = ChatSession(
        id=str(uuid.uuid4()), user_id=test_user_2.id, title="Test Session"
    )
    db_session.add(session)
    await db_session.commit()

    # User 1 logs in
    login_response = await async_client.post(
        "/users/login",
        json={"email": "auth_test@example.com", "password": "password123"},
    )
    token = login_response.json()["access_token"]

    # User 1 tries to fetch their sessions, it should not include User 2's session
    response = await async_client.get(
        "/chat/sessions", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


async def test_accessing_another_users_messages(
    async_client, db_session, test_user, test_user_2
):
    # User 2 creates a session and message
    session = ChatSession(
        id=str(uuid.uuid4()), user_id=test_user_2.id, title="Test Session"
    )
    db_session.add(session)
    msg = Message(
        id=str(uuid.uuid4()),
        user_id=test_user_2.id,
        session_id=session.id,
        role="user",
        content="Hello",
    )
    db_session.add(msg)
    await db_session.commit()

    # User 1 logs in
    login_response = await async_client.post(
        "/users/login",
        json={"email": "auth_test@example.com", "password": "password123"},
    )
    token = login_response.json()["access_token"]

    # User 1 tries to fetch User 2's session messages
    response = await async_client.get(
        f"/chat/sessions/{session.id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"
