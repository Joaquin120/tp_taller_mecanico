import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.auth import UsuarioActual, get_current_user
from app.core.database import get_session
from app.modules.usuarios.models import EventoSeguridad
from app.modules.usuarios.router import get_usuarios_uow
from app.modules.usuarios.service import (
    ACCION_ALTA_USUARIO,
    ACCION_ASIGNACION_ROL,
    ACCION_REVOCACION_ROL,
)
from main import app


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_for_eventos_router_123")
    app.state.dummy_hash = "$2b$04$dummyhashfordefensetimingtestingonly1234567890123456789012"
    app.state.session_factory = MagicMock()


@pytest.mark.asyncio
async def test_listar_eventos_admin_exitoso():
    admin = UsuarioActual(
        id=1,
        email="admin@test.com",
        nombre="Admin",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
    )

    app.dependency_overrides[get_current_user] = lambda: admin

    mock_eventos = [
        EventoSeguridad(
            id=2,
            cuando=datetime.now(timezone.utc),
            actor="admin@test.com",
            accion=ACCION_ASIGNACION_ROL,
        ),
        EventoSeguridad(
            id=1,
            cuando=datetime.now(timezone.utc),
            actor="admin@test.com",
            accion=ACCION_ALTA_USUARIO,
        ),
    ]

    mock_uow = AsyncMock()
    mock_uow.eventos.count = AsyncMock(return_value=2)
    mock_uow.eventos.listar_paginado = AsyncMock(return_value=mock_eventos)

    async def override_uow():
        yield mock_uow

    app.dependency_overrides[get_usuarios_uow] = override_uow

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/eventos?page=1&size=10")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["size"] == 10
        assert data["pages"] == 1
        assert len(data["items"]) == 2
        assert data["items"][0]["accion"] == ACCION_ASIGNACION_ROL
        assert data["items"][1]["accion"] == ACCION_ALTA_USUARIO
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_usuarios_uow, None)


@pytest.mark.asyncio
async def test_listar_eventos_no_admin_responde_403():
    mecanico = UsuarioActual(
        id=2,
        email="mecanico@test.com",
        nombre="Mecanico",
        activo=True,
        debe_cambiar_password=False,
        roles=["MECANICO"],
    )

    app.dependency_overrides[get_current_user] = lambda: mecanico

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/eventos")

        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_listar_eventos_debe_cambiar_password_responde_403():
    admin_pendiente = UsuarioActual(
        id=1,
        email="admin_nuevo@test.com",
        nombre="Admin Nuevo",
        activo=True,
        debe_cambiar_password=True,
        roles=["ADMIN"],
    )

    app.dependency_overrides[get_current_user] = lambda: admin_pendiente

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/eventos")

        assert response.status_code == 403
        assert "contraseña" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_listar_eventos_sin_sesion_responde_401():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/eventos")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_listar_eventos_pagina_fuera_de_rango_422():
    admin = UsuarioActual(
        id=1,
        email="admin@test.com",
        nombre="Admin",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
    )

    app.dependency_overrides[get_current_user] = lambda: admin

    mock_uow = AsyncMock()
    mock_uow.eventos.count = AsyncMock(return_value=1)
    mock_uow.eventos.listar_paginado = AsyncMock(return_value=[])

    async def override_uow():
        yield mock_uow

    app.dependency_overrides[get_usuarios_uow] = override_uow

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/eventos?page=5&size=10")

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_usuarios_uow, None)


@pytest.mark.asyncio
async def test_listar_eventos_size_invalido_422():
    admin = UsuarioActual(
        id=1,
        email="admin@test.com",
        nombre="Admin",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
    )

    app.dependency_overrides[get_current_user] = lambda: admin

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # size mayor a 100
            response = await client.get("/eventos?page=1&size=500")

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_listar_eventos_tabla_vacia_200():
    admin = UsuarioActual(
        id=1,
        email="admin@test.com",
        nombre="Admin",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
    )

    app.dependency_overrides[get_current_user] = lambda: admin

    mock_uow = AsyncMock()
    mock_uow.eventos.count = AsyncMock(return_value=0)
    mock_uow.eventos.listar_paginado = AsyncMock(return_value=[])

    async def override_uow():
        yield mock_uow

    app.dependency_overrides[get_usuarios_uow] = override_uow

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/eventos?page=1&size=20")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["pages"] == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_usuarios_uow, None)
