import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, Request
import pytest
import jwt

from app.core.auth import (
    UsuarioActual,
    get_current_user,
    get_usuario_actual,
    require_roles,
    requiere_rol,
)
from app.core.security import crear_access_token
from app.modules.usuarios.models import Usuario


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_jwt_secret_key_1234567890")


def crear_request_con_cookie(cookie_val: str | None) -> Request:
    request = MagicMock(spec=Request)
    if cookie_val is not None:
        request.cookies = {"access_token": cookie_val}
    else:
        request.cookies = {}
    return request


@pytest.mark.asyncio
async def test_get_current_user_sin_cookie_lanza_401():
    request = crear_request_con_cookie(None)
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, session)

    assert exc_info.value.status_code == 401
    assert "cookie" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_token_invalido_lanza_401():
    request = crear_request_con_cookie("token.malformado.invalido")
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, session)

    assert exc_info.value.status_code == 401
    assert "inválido" in exc_info.value.detail.lower() or "malformado" in exc_info.value.detail.lower() or "malformado" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_token_expirado_lanza_401():
    token_expirado = crear_access_token(
        {"sub": "usuario@test.com"},
        expires_delta=timedelta(seconds=-30),
    )
    request = crear_request_con_cookie(token_expirado)
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, session)

    assert exc_info.value.status_code == 401
    assert "expirada" in exc_info.value.detail.lower() or "caducado" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_token_sin_sub_lanza_401():
    from app.core.config import get_settings
    settings = get_settings()
    token_sin_sub = jwt.encode(
        {"roles": ["CLIENTE"], "exp": (datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    request = crear_request_con_cookie(token_sin_sub)
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, session)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_usuario_no_encontrado_lanza_401():
    token = crear_access_token({"sub": "noexiste@test.com"})
    request = crear_request_con_cookie(token)

    mock_session = AsyncMock()
    mock_res_user = MagicMock()
    mock_res_user.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_res_user

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, mock_session)

    assert exc_info.value.status_code == 401
    assert "inactivo" in exc_info.value.detail.lower() or "no encontrado" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_usuario_inactivo_lanza_401():
    token = crear_access_token({"sub": "inactivo@test.com"})
    request = crear_request_con_cookie(token)

    usuario_inactivo = Usuario(
        id=1,
        email="inactivo@test.com",
        nombre="Inactivo",
        password_hash="hash",
        activo=False,
    )

    mock_session = AsyncMock()
    mock_res_user = MagicMock()
    mock_res_user.scalar_one_or_none.return_value = usuario_inactivo
    mock_session.execute.return_value = mock_res_user

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, mock_session)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_exitoso_con_roles_vigentes_de_bd():
    token = crear_access_token({"sub": "activo@test.com", "roles": ["CLIENTE"]})
    request = crear_request_con_cookie(token)

    usuario = Usuario(
        id=10,
        email="activo@test.com",
        nombre="Usuario Activo",
        password_hash="hash",
        activo=True,
        debe_cambiar_password=False,
    )

    mock_session = AsyncMock()
    # Mocking calls to session.execute:
    # 1. usuario
    mock_res_user = MagicMock()
    mock_res_user.scalar_one_or_none.return_value = usuario

    # 2. roles vigentes
    mock_res_roles = MagicMock()
    mock_res_roles.scalars.return_value.all.return_value = ["MECANICO", "ADMIN"]

    # 3. cliente_id
    mock_res_cliente = MagicMock()
    mock_res_cliente.scalar_one_or_none.return_value = 55

    mock_session.execute.side_effect = [mock_res_user, mock_res_roles, mock_res_cliente]

    user_actual = await get_current_user(request, mock_session)

    assert isinstance(user_actual, UsuarioActual)
    assert user_actual.id == 10
    assert user_actual.email == "activo@test.com"
    # Roles vigentes son de la BD, no los del token!
    assert user_actual.roles == ["MECANICO", "ADMIN"]
    assert user_actual.roles_token == ["CLIENTE"]
    assert user_actual.cliente_id == 55


@pytest.mark.asyncio
async def test_require_roles_permiso_concedido():
    user = UsuarioActual(
        id=1,
        email="admin@test.com",
        nombre="Admin",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
    )

    checker = require_roles("ADMIN", "MECANICO")
    resultado = await checker(usuario=user)
    assert resultado is user


@pytest.mark.asyncio
async def test_require_roles_permiso_denegado_lanza_403():
    user = UsuarioActual(
        id=2,
        email="cliente@test.com",
        nombre="Cliente",
        activo=True,
        debe_cambiar_password=False,
        roles=["CLIENTE"],
    )

    checker = require_roles("ADMIN", "RECEPCION")
    with pytest.raises(HTTPException) as exc_info:
        await checker(usuario=user)

    assert exc_info.value.status_code == 403
    assert "insuficientes" in exc_info.value.detail.lower()


def test_aliases_en_espanol():
    assert get_usuario_actual is get_current_user
    assert requiere_rol is require_roles

@pytest.mark.asyncio
async def test_get_current_user_iat_anterior_al_cambio_lanza_401():
    referencia = datetime(2026, 1, 1, 12, 0, 0, 500000, tzinfo=timezone.utc)
    token = crear_access_token(
        {"sub": "activo@test.com"},
        emitido_en=referencia - timedelta(seconds=1),
    )
    request = crear_request_con_cookie(token)

    usuario = Usuario(
        id=10,
        email="activo@test.com",
        nombre="Usuario Activo",
        password_hash="hash",
        activo=True,
        debe_cambiar_password=False,
        password_cambiada_en=referencia,
    )

    mock_session = AsyncMock()
    mock_res_user = MagicMock()
    mock_res_user.scalar_one_or_none.return_value = usuario
    mock_session.execute.return_value = mock_res_user

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, mock_session)

    assert exc_info.value.status_code == 401
    assert "invalidada" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_mismo_segundo_fraccion_anterior_lanza_401():
    referencia = datetime(2026, 1, 1, 12, 0, 0, 900000, tzinfo=timezone.utc)
    token = crear_access_token(
        {"sub": "activo@test.com"},
        emitido_en=referencia - timedelta(microseconds=100000),
    )
    request = crear_request_con_cookie(token)

    usuario = Usuario(
        id=10,
        email="activo@test.com",
        nombre="Usuario Activo",
        password_hash="hash",
        activo=True,
        debe_cambiar_password=False,
        password_cambiada_en=referencia,
    )

    mock_session = AsyncMock()
    mock_res_user = MagicMock()
    mock_res_user.scalar_one_or_none.return_value = usuario
    mock_session.execute.return_value = mock_res_user

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, mock_session)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_iat_igual_al_cambio_es_valido():
    referencia = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
    token = crear_access_token({"sub": "activo@test.com"}, emitido_en=referencia)
    request = crear_request_con_cookie(token)

    usuario = Usuario(
        id=10,
        email="activo@test.com",
        nombre="Usuario Activo",
        password_hash="hash",
        activo=True,
        debe_cambiar_password=False,
        password_cambiada_en=referencia,
    )

    mock_session = AsyncMock()
    mock_res_user = MagicMock()
    mock_res_user.scalar_one_or_none.return_value = usuario
    mock_res_roles = MagicMock()
    mock_res_roles.scalars.return_value.all.return_value = ["ADMIN"]
    mock_res_cliente = MagicMock()
    mock_res_cliente.scalar_one_or_none.return_value = None
    mock_session.execute.side_effect = [mock_res_user, mock_res_roles, mock_res_cliente]

    user_actual = await get_current_user(request, mock_session)

    assert user_actual.roles == ["ADMIN"]


@pytest.mark.asyncio
async def test_get_current_user_cambiada_en_naive_se_normaliza_a_utc():
    referencia_naive = datetime(2026, 1, 1, 12, 0, 0, 500000)
    token = crear_access_token(
        {"sub": "activo@test.com"},
        emitido_en=referencia_naive.replace(tzinfo=timezone.utc) + timedelta(seconds=1),
    )
    request = crear_request_con_cookie(token)

    usuario = Usuario(
        id=10,
        email="activo@test.com",
        nombre="Usuario Activo",
        password_hash="hash",
        activo=True,
        debe_cambiar_password=False,
        password_cambiada_en=referencia_naive,
    )

    mock_session = AsyncMock()
    mock_res_user = MagicMock()
    mock_res_user.scalar_one_or_none.return_value = usuario
    mock_res_roles = MagicMock()
    mock_res_roles.scalars.return_value.all.return_value = ["CLIENTE"]
    mock_res_cliente = MagicMock()
    mock_res_cliente.scalar_one_or_none.return_value = None
    mock_session.execute.side_effect = [mock_res_user, mock_res_roles, mock_res_cliente]

    user_actual = await get_current_user(request, mock_session)

    assert user_actual.email == "activo@test.com"


@pytest.mark.asyncio
async def test_requiere_password_actualizada_bloquea_bandera_activa():
    from app.core.auth import requiere_password_actualizada

    user = UsuarioActual(
        id=1,
        email="nuevo@test.com",
        nombre="Nuevo",
        activo=True,
        debe_cambiar_password=True,
        roles=["MECANICO"],
    )

    with pytest.raises(HTTPException) as exc_info:
        await requiere_password_actualizada(usuario=user)

    assert exc_info.value.status_code == 403
    assert "contraseña" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_requiere_password_actualizada_permite_bandera_apagada():
    from app.core.auth import requiere_password_actualizada

    user = UsuarioActual(
        id=1,
        email="listo@test.com",
        nombre="Listo",
        activo=True,
        debe_cambiar_password=False,
        roles=["MECANICO"],
    )

    resultado = await requiere_password_actualizada(usuario=user)
    assert resultado is user
