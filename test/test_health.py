from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
import pytest

from app.core.config import Settings
from app.core.database import get_session
from main import app


@pytest.mark.asyncio
async def test_health_live() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "alive": True}


@pytest.mark.asyncio
async def test_health_ready_success() -> None:
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")

        assert response.status_code == 200
        assert response.json() == {"status": "ready", "database": "connected"}
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_health_ready_database_error() -> None:
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        side_effect=ConnectionRefusedError("Database unreachable")
    )

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {"detail": "Base de datos no disponible"}
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_get_session_yields_session() -> None:
    mock_session = AsyncMock()
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__.return_value = mock_session
    mock_context_manager.__aexit__.return_value = None

    mock_factory = MagicMock(return_value=mock_context_manager)
    mock_request = MagicMock()
    mock_request.app.state.session_factory = mock_factory

    generator = get_session(mock_request)
    session = await anext(generator)
    assert session is mock_session
    await generator.aclose()


@pytest.mark.asyncio
async def test_lifespan_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "secret_jwt")

    from main import lifespan

    test_app = FastAPI()
    mock_engine = AsyncMock()
    mock_factory = MagicMock()

    with monkeypatch.context() as m:
        m.setattr("main.crear_motor", MagicMock(return_value=mock_engine))
        m.setattr("main.crear_fabrica_sesiones", MagicMock(return_value=mock_factory))

        async with lifespan(test_app):
            assert test_app.state.engine is mock_engine
            assert test_app.state.session_factory is mock_factory
            assert hasattr(test_app.state, "dummy_hash")
            assert len(test_app.state.dummy_hash) > 0

        mock_engine.dispose.assert_awaited_once()


def test_settings_computed_database_url() -> None:
    settings = Settings(
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_HOST="db_host",
        POSTGRES_PORT=5433,
        POSTGRES_DB="test_db",
        JWT_SECRET_KEY="secret_key",
        _env_file=None,
    )
    assert (
        settings.database_url
        == "postgresql+asyncpg://test_user:test_password@db_host:5433/test_db"
    )


def test_settings_missing_postgres_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(JWT_SECRET_KEY="secret_key", _env_file=None)

    errors = exc_info.value.errors()
    assert any(err["loc"] == ("POSTGRES_PASSWORD",) for err in errors)


def test_settings_missing_jwt_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(POSTGRES_PASSWORD="password", _env_file=None)

    errors = exc_info.value.errors()
    assert any(err["loc"] == ("JWT_SECRET_KEY",) for err in errors)
