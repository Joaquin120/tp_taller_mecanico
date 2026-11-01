import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.auth import UsuarioActual, get_current_user
from app.modules.usuarios.models import AsignacionRol, Usuario
from app.modules.usuarios.router import get_usuarios_uow
from app.modules.usuarios.schemas import AsignarRolRequest, CrearUsuarioRequest
from app.modules.usuarios.service import PersonalService
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork
from main import app


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_for_personal_router_123")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    app.state.dummy_hash = "$2b$04$dummyhashfordefensetimingtestingonly1234567890123456789012"
    app.state.session_factory = MagicMock()


def mock_admin(id: int = 1) -> UsuarioActual:
    return UsuarioActual(
        id=id,
        email=f"admin_{id}@test.com",
        nombre="Admin",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
    )


# -------------------------------------------------------------
# POST /usuarios
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_crear_usuario_personal_exitoso():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    mock_usuario = Usuario(
        id=50,
        email="nuevo_mecanico@test.com",
        nombre="Pedro Gomez",
        password_hash="hashed_pw",
        activo=True,
        debe_cambiar_password=True,
    )

    with patch.object(PersonalService, "crear_usuario", return_value=(mock_usuario, ["MECANICO"])):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/usuarios",
                json={
                    "email": "nuevo_mecanico@test.com",
                    "nombre": "Pedro Gomez",
                    "password": "PasswordProvisoria1",
                    "rol": "MECANICO",
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 50
    assert data["email"] == "nuevo_mecanico@test.com"
    assert data["debe_cambiar_password"] is True
    assert data["roles"] == ["MECANICO"]
    assert "password" not in data
    assert "password_hash" not in data
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_crear_usuario_rol_no_admin_responde_403():
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
            response = await client.post(
                "/usuarios",
                json={
                    "email": "otro@test.com",
                    "nombre": "Otro",
                    "password": "Password123",
                    "rol": "MECANICO",
                },
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_crear_usuario_sin_sesion_responde_401():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/usuarios",
            json={
                "email": "otro@test.com",
                "nombre": "Otro",
                "password": "Password123",
                "rol": "MECANICO",
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_crear_usuario_rol_invalido_responde_422():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/usuarios",
                json={
                    "email": "otro@test.com",
                    "nombre": "Otro",
                    "password": "Password123",
                    "rol": "CLIENTE",  # CLIENTE no es rol de personal
                },
            )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# -------------------------------------------------------------
# GET /usuarios/{id}/roles
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_listar_roles_usuario_exitoso():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    ahora = datetime.now(timezone.utc)
    mock_asignaciones = [
        AsignacionRol(
            id=10,
            usuario_id=2,
            rol="MECANICO",
            desde=ahora,
            vence_en=None,
            revocada_en=None,
            otorgada_por=1,
        ),
        AsignacionRol(
            id=9,
            usuario_id=2,
            rol="RECEPCION",
            desde=ahora - timedelta(days=60),
            vence_en=None,
            revocada_en=ahora - timedelta(days=10),
            otorgada_por=1,
        ),
    ]

    mock_uow = AsyncMock()
    mock_uow.usuarios.get_by_id = AsyncMock(return_value=Usuario(id=2, email="u2@test.com", nombre="U2", password_hash="h", activo=True))
    mock_uow.roles.listar_por_usuario = AsyncMock(return_value=mock_asignaciones)

    app.dependency_overrides[get_usuarios_uow] = lambda: mock_uow

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/usuarios/2/roles")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["rol"] == "MECANICO"
        assert data[0]["vigente"] is True
        assert data[1]["rol"] == "RECEPCION"
        assert data[1]["vigente"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_usuarios_uow, None)


@pytest.mark.asyncio
async def test_listar_roles_usuario_inexistente_404():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    mock_uow = AsyncMock()
    mock_uow.usuarios.get_by_id = AsyncMock(return_value=None)
    app.dependency_overrides[get_usuarios_uow] = lambda: mock_uow

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/usuarios/999/roles")

        assert response.status_code == 404
        assert "no encontrado" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_usuarios_uow, None)


# -------------------------------------------------------------
# POST /usuarios/{id}/roles
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_asignar_rol_exitoso():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    ahora = datetime.now(timezone.utc)
    futuro = ahora + timedelta(days=30)
    mock_asig = AsignacionRol(
        id=15,
        usuario_id=2,
        rol="MECANICO",
        desde=ahora,
        vence_en=futuro,
        revocada_en=None,
        otorgada_por=1,
    )

    with patch.object(PersonalService, "asignar_rol", return_value=mock_asig):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/usuarios/2/roles",
                json={
                    "rol": "MECANICO",
                    "vence_en": futuro.isoformat(),
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 15
        assert data["rol"] == "MECANICO"
        assert data["vigente"] is True
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_asignar_rol_vencimiento_naive_responde_422():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/usuarios/2/roles",
                json={
                    "rol": "MECANICO",
                    "vence_en": "2027-01-01T12:00:00",  # Sin zona horaria
                },
            )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_asignar_rol_ya_vigente_responde_409():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    with patch.object(
        PersonalService,
        "asignar_rol",
        side_effect=HTTPException(status_code=409, detail="El usuario ya posee ese rol vigente"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/usuarios/2/roles",
                json={"rol": "MECANICO"},
            )
        assert response.status_code == 409
        assert "vigente" in response.json()["detail"].lower()
    app.dependency_overrides.pop(get_current_user, None)


# -------------------------------------------------------------
# DELETE /usuarios/{id}/roles/{rol}
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_revocar_rol_exitoso():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    ahora = datetime.now(timezone.utc)
    mock_asig = AsignacionRol(
        id=20,
        usuario_id=2,
        rol="MECANICO",
        desde=ahora - timedelta(days=10),
        revocada_en=ahora,
    )

    with patch.object(PersonalService, "revocar_rol", return_value=mock_asig):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.delete("/usuarios/2/roles/MECANICO")

        assert response.status_code == 200
        data = response.json()
        assert data["rol"] == "MECANICO"
        assert "revocado" in data["mensaje"].lower()
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_revocar_rol_autoproteccion_admin_409():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    with patch.object(
        PersonalService,
        "revocar_rol",
        side_effect=HTTPException(
            status_code=409,
            detail="Un administrador no puede revocar su propio rol ADMIN",
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # admin 1 intenta revocarse a sí mismo
            response = await client.delete("/usuarios/1/roles/ADMIN")

        assert response.status_code == 409
        assert "propio rol admin" in response.json()["detail"].lower()
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_revocar_rol_ultimo_admin_vigente_409():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    with patch.object(
        PersonalService,
        "revocar_rol",
        side_effect=HTTPException(
            status_code=409,
            detail="El sistema no puede quedar sin administradores vigentes",
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # admin 1 intenta revocar al admin 2, pero no quedan más admins
            response = await client.delete("/usuarios/2/roles/ADMIN")

        assert response.status_code == 409
        assert "sin administradores vigentes" in response.json()["detail"].lower()
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_revocar_rol_no_existente_404():
    admin = mock_admin(1)
    app.dependency_overrides[get_current_user] = lambda: admin

    with patch.object(
        PersonalService,
        "revocar_rol",
        side_effect=HTTPException(
            status_code=404,
            detail="Asignación de rol no encontrada",
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.delete("/usuarios/2/roles/ROL_INEXISTENTE")

        assert response.status_code == 404
    app.dependency_overrides.pop(get_current_user, None)


# -------------------------------------------------------------
# Concurrencia de Reasignación de Rol
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrencia_reasignacion_rol_uno_gana_y_otro_choca_409():
    """Simula dos peticiones concurrentes de asignación de rol sobre el mismo usuario.
    
    Una logra completar la asignación (201) y la otra recibe 409 por el índice
    único parcial uq_asignacion_rol_activa (o chequeo for_update).
    """
    admin = mock_admin(1)
    session = AsyncMock()
    uow1 = UsuariosUnitOfWork(session)
    uow2 = UsuariosUnitOfWork(session)

    dto = AsignarRolRequest(rol="MECANICO", vence_en=None)

    # Simular que uow1 gana y uow2 detecta rol vigente
    uow1.usuarios.get_by_id = AsyncMock(return_value=Usuario(id=3, email="u3@test.com", nombre="U3", password_hash="h", activo=True))
    uow1.roles.get_abierta = AsyncMock(return_value=None)
    mock_nueva_asig = AsignacionRol(id=101, usuario_id=3, rol="MECANICO")
    uow1.roles.add = AsyncMock(return_value=mock_nueva_asig)
    uow1.eventos.add = AsyncMock()

    uow2.usuarios.get_by_id = AsyncMock(return_value=Usuario(id=3, email="u3@test.com", nombre="U3", password_hash="h", activo=True))
    # uow2 ve que ya hay una asignación vigente creada por uow1
    uow2.roles.get_abierta = AsyncMock(return_value=mock_nueva_asig)

    resultado1 = await PersonalService.asignar_rol(3, dto, admin, uow1)
    assert resultado1.id == 101

    with pytest.raises(HTTPException) as exc_info:
        await PersonalService.asignar_rol(3, dto, admin, uow2)

    assert exc_info.value.status_code == 409
    assert "vigente" in exc_info.value.detail.lower()
