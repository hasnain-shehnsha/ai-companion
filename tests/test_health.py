from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_liveness_probe():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_readiness_probe_success(mocker):
    # Mock PostgreSQL
    mock_db = AsyncMock()
    mock_db.execute.return_value = True

    async def override_get_db():
        yield mock_db

    from app.core.database import get_db

    app.dependency_overrides[get_db] = override_get_db

    # Mock Redis
    mocker.patch("app.api.endpoints.health.redis_client.ping", new_callable=AsyncMock)

    # Mock Qdrant
    mock_qdrant = mocker.patch("app.api.endpoints.health.memory_service")
    mock_qdrant.client.get_collections = mocker.MagicMock()

    # Mock config to simulate valid production settings
    mocker.patch("app.api.endpoints.health.settings.ENVIRONMENT", "production")
    mocker.patch("app.api.endpoints.health.settings.SECRET_KEY", "real-secure-key")
    mocker.patch("app.api.endpoints.health.settings.RESEND_API_KEY", "re_123")
    mocker.patch("app.api.endpoints.health.settings.WHATSAPP_TOKEN", "EAA...")
    mocker.patch(
        "app.api.endpoints.health.settings.RESEND_FROM_EMAIL", "test@example.com"
    )
    mocker.patch("app.api.endpoints.health.settings.RESEND_FROM_NAME", "AI")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_readiness_probe_failure_db_and_redis(mocker):
    # Mock PostgreSQL failure
    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("DB Down")

    async def override_get_db():
        yield mock_db

    from app.core.database import get_db

    app.dependency_overrides[get_db] = override_get_db

    # Mock Redis failure
    mocker.patch(
        "app.api.endpoints.health.redis_client.ping",
        side_effect=Exception("Redis Down"),
    )

    # Qdrant failure
    mock_qdrant = mocker.patch("app.api.endpoints.health.memory_service")
    mock_qdrant.client.get_collections.side_effect = Exception("Qdrant Down")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["status"] == "error"
        issues = data["detail"]["issues"]
        assert "PostgreSQL unreachable" in issues
        assert "Redis unreachable" in issues
        assert "Qdrant unreachable" in issues

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_readiness_probe_production_missing_config(mocker):
    # Success DB and Redis
    mock_db = AsyncMock()
    mock_db.execute.return_value = True

    async def override_get_db():
        yield mock_db

    from app.core.database import get_db

    app.dependency_overrides[get_db] = override_get_db

    mocker.patch("app.api.endpoints.health.redis_client.ping", new_callable=AsyncMock)
    mock_qdrant = mocker.patch("app.api.endpoints.health.memory_service")
    mock_qdrant.client.get_collections = mocker.MagicMock()

    # Simulate production missing some keys
    mocker.patch("app.api.endpoints.health.settings.ENVIRONMENT", "production")
    mocker.patch(
        "app.api.endpoints.health.settings.SECRET_KEY", "testsecret12345"
    )  # Default invalid
    mocker.patch("app.api.endpoints.health.settings.RESEND_API_KEY", "")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["status"] == "error"
        issues = data["detail"]["issues"]
        assert "Invalid SECRET_KEY in production" in issues
        assert "Missing RESEND_API_KEY in production" in issues

    app.dependency_overrides.clear()
