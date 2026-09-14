import pytest
from app.models.user import User


async def test_successful_registration(async_client):
    response = await async_client.post(
        "/users/",
        json={
            "email": "new_user@example.com",
            "password": "strongpassword123",
            "first_name": "Test",
            "last_name": "User",
            "whatsapp_number": "+923001234567",
            "timezone": "UTC",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new_user@example.com"
    assert "id" in data


async def test_duplicate_email(async_client):
    # First registration
    await async_client.post(
        "/users/",
        json={
            "email": "duplicate@example.com",
            "password": "strongpassword123",
            "first_name": "Duplicate",
            "last_name": "User",
            "whatsapp_number": "+923001234568",
        },
    )

    # Second registration with same email
    response = await async_client.post(
        "/users/",
        json={
            "email": "duplicate@example.com",
            "password": "anotherpassword",
            "first_name": "Duplicate",
            "last_name": "User",
            "whatsapp_number": "+923001234569",
        },
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_duplicate_whatsapp_number(async_client):
    # First registration
    await async_client.post(
        "/users/",
        json={
            "email": "user1@example.com",
            "password": "strongpassword123",
            "first_name": "User1",
            "last_name": "Test",
            "whatsapp_number": "+923001234570",
        },
    )

    # Second registration with same WhatsApp number
    response = await async_client.post(
        "/users/",
        json={
            "email": "user2@example.com",
            "password": "anotherpassword",
            "first_name": "User2",
            "last_name": "Test",
            "whatsapp_number": "+923001234570",
        },
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_password_validation(async_client):
    # Pydantic schemas usually validate lengths, if there's no custom logic, let's see if short passwords fail or succeed.
    # We will test missing password instead as a basic validation check.
    response = await async_client.post(
        "/users/",
        json={"email": "nopassword@example.com", "whatsapp_number": "+888888888"},
    )
    assert response.status_code == 422  # Unprocessable Entity
