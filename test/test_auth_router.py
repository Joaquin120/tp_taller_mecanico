import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
import pytest

from app.core.auth import UsuarioActual, get_current_user
from app.core.database import get_session
from app.core.security import crear_access_token, hash_password
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.router import get_usuarios_uow
from app.modules.usuarios.service import AuthService
from main import app


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_for_auth_router_123456789")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    app.state.dummy_hash = "$2b$04$dummyhashfordefensetimingtestingonly1234567890123456789012"
    app.state.session_factory = MagicMock()


@pytest.mark.asyncio
async def test_registro_cliente_exitoso():
    mock_usuario = Usuario(
        id=1,
        email="cliente@test.com",
        nombre="Cliente Feliz",
        password_hash="hashed_pw",
        activo=True,
    )

    async def mock_registrar(dto, uow):
        return mock_usuario, ["CLIENTE"], 10

    mock_uow = AsyncMock()

    async def override_uow():
        yield mock_uow

    app.dependency_overrides[get_usuarios_uow] = override_uow

    try:
        from unittest.mock import patch
        with patch.object(AuthService, "registrar_cliente", side_effect=mock_registrar):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/auth/registro",
                    json={
                        "email": "cliente@test.com",
                        "password": "PasswordValido123",
                        "nombre": "Cliente Feliz",
                        "documento": "12345678",
                        "telefono": "1144556677",
                    },
                )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 1
        assert data["email"] == "cliente@test.com"
        assert data["nombre"] == "Cliente Feliz"
        assert data["roles"] == ["CLIENTE"]
        assert data["cliente_id"] == 10
        assert "password" not in data
        assert "password_hash" not in data
    finally:
        app.dependency_overrides.pop(get_usuarios_uow, None)


@pytest.mark.asyncio
async def test_registro_cliente_email_duplicado_409():
    mock_uow = AsyncMock()

    async def override_uow():
        yield mock_uow

    app.dependency_overrides[get_usuarios_uow] = override_uow

    try:
        from unittest.mock import patch
        with patch.object(
            AuthService,
            "registrar_cliente",
            side_effect=HTTPException(status_code=409, detail="El correo ya se encuentra registrado"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/auth/registro",
                    json={
                        "email": "duplicado@test.com",
                        "password": "PasswordValido123",
                        "nombre": "Cliente Duplicado",
                        "documento": "12345678",
                        "telefono": "1144556677",
                    },
                )

        assert response.status_code == 409
        assert "correo ya se encuentra registrado" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_usuarios_uow, None)


@pytest.mark.asyncio
async def test_login_exitoso_set_cookie_sin_token_en_body():
    mock_usuario = Usuario(
        id=5,
        email="login_ok@test.com",
        nombre="Usuario Logueado",
        password_hash="hash",
        activo=True,
    )
    fake_token = crear_access_token({"sub": "login_ok@test.com", "roles": ["CLIENTE"]})

    async def mock_login(email, password, ip, *args, **kwargs):
        return mock_usuario, fake_token, ["CLIENTE"]

    from unittest.mock import patch
    with patch.object(AuthService, "login", side_effect=mock_login):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/login",
                json={
                    "email": "login_ok@test.com",
                    "password": "MiPasswordCorrecto",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "login_ok@test.com"
    assert data["roles"] == ["CLIENTE"]
    # Regla dura: El JWT jamás se expone en el body de respuesta (DD-02)
    assert "token" not in data
    assert "access_token" not in data

    # Verificamos que la cabecera Set-Cookie contenga la cookie HttpOnly
    assert "set-cookie" in response.headers
    cookie_header = response.headers["set-cookie"]
    assert "access_token=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header or "samesite=lax" in cookie_header


@pytest.mark.asyncio
async def test_login_credenciales_invalidas_401():
    from unittest.mock import patch
    with patch.object(
        AuthService,
        "login",
        side_effect=HTTPException(status_code=401, detail="Credenciales inválidas"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/login",
                json={
                    "email": "login_fail@test.com",
                    "password": "PasswordInvalido",
                },
            )

    assert response.status_code == 401
    assert "Credenciales inválidas" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_rate_limit_429():
    from unittest.mock import patch
    with patch.object(
        AuthService,
        "login",
        side_effect=HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Intente nuevamente en 60 segundos.",
            headers={"Retry-After": "60"},
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/login",
                json={
                    "email": "bloqueado@test.com",
                    "password": "Password",
                },
            )

    assert response.status_code == 429
    assert response.headers.get("retry-after") == "60"


@pytest.mark.asyncio
async def test_logout_elimina_cookie():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"mensaje": "Sesión cerrada correctamente"}
    assert "set-cookie" in response.headers
    cookie_header = response.headers["set-cookie"]
    # Comprobar que borra la cookie estableciendo max-age=0 o fecha expirada
    assert "max-age=0" in cookie_header.lower() or 'access_token=""' in cookie_header


@pytest.mark.asyncio
async def test_yo_sin_cookie_devuelve_401():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/auth/yo")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_yo_con_cookie_valida_devuelve_usuario_y_roles():
    mock_user_actual = UsuarioActual(
        id=42,
        email="yo@test.com",
        nombre="Soy Yo",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN", "MECANICO"],
        roles_token=["ADMIN"],
        cliente_id=None,
    )

    async def override_current_user():
        return mock_user_actual

    app.dependency_overrides[get_current_user] = override_current_user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/auth/yo")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert data["email"] == "yo@test.com"
        assert data["nombre"] == "Soy Yo"
        assert data["roles"] == ["ADMIN", "MECANICO"]
        assert data["roles_token"] == ["ADMIN"]
        assert data["debe_cambiar_password"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_login_repetido_6_veces_dispara_429_en_el_sexto():
    intentos_fallidos = 0

    async def mock_login_simulado(email, password, ip, *args, **kwargs):
        nonlocal intentos_fallidos
        if intentos_fallidos >= 5:
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos fallidos. Intente nuevamente en 60 segundos.",
                headers={"Retry-After": "60"},
            )
        intentos_fallidos += 1
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    from unittest.mock import patch
    with patch.object(AuthService, "login", side_effect=mock_login_simulado):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Los primeros 5 devuelven 401
            for _ in range(5):
                res = await client.post(
                    "/auth/login",
                    json={"email": "brute@test.com", "password": "Wrong"},
                )
                assert res.status_code == 401

            # El 6to intento dispara 429
            res_6 = await client.post(
                "/auth/login",
                json={"email": "brute@test.com", "password": "Wrong"},
            )
            assert res_6.status_code == 429
            assert res_6.headers.get("retry-after") == "60"



@pytest.mark.asyncio
async def test_cambiar_password_exitoso_emite_cookie_y_actualiza():
    user = UsuarioActual(
        id=7,
        email="cambio@test.com",
        nombre="Usuario Cambio",
        activo=True,
        debe_cambiar_password=True,
        roles=["MECANICO"],
    )
    app.dependency_overrides[get_current_user] = lambda: user

    mock_uow = AsyncMock()
    app.dependency_overrides[get_usuarios_uow] = lambda: mock_uow

    nuevo_token = crear_access_token({"sub": "cambio@test.com", "roles": ["MECANICO"]})
    mock_user_ret = Usuario(id=7, email="cambio@test.com", nombre="Usuario Cambio", password_hash="new_h", activo=True, debe_cambiar_password=False)

    try:
        with patch.object(AuthService, "cambiar_password", return_value=(mock_user_ret, nuevo_token)):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/auth/cambiar-password",
                    json={
                        "password_actual": "PasswordAnterior123",
                        "password_nueva": "PasswordNueva123!",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["debe_cambiar_password"] is False
        assert "actualizada" in data["mensaje"].lower()
        assert "set-cookie" in response.headers
        assert "access_token=" in response.headers["set-cookie"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cambiar_password_clave_actual_incorrecta_401():
    user = UsuarioActual(
        id=7,
        email="cambio@test.com",
        nombre="Usuario Cambio",
        activo=True,
        debe_cambiar_password=True,
        roles=["MECANICO"],
    )
    app.dependency_overrides[get_current_user] = lambda: user
    mock_uow = AsyncMock()
    app.dependency_overrides[get_usuarios_uow] = lambda: mock_uow

    try:
        with patch.object(
            AuthService,
            "cambiar_password",
            side_effect=HTTPException(status_code=401, detail="La contraseña actual es incorrecta"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/auth/cambiar-password",
                    json={
                        "password_actual": "PasswordErronea123",
                        "password_nueva": "PasswordNueva123!",
                    },
                )

        assert response.status_code == 401
        assert "incorrecta" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cambiar_password_sin_sesion_responde_401():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/auth/cambiar-password",
            json={
                "password_actual": "Password123",
                "password_nueva": "PasswordNueva123",
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cambiar_password_nueva_invalida_422():
    user = UsuarioActual(
        id=7,
        email="cambio@test.com",
        nombre="Usuario Cambio",
        activo=True,
        debe_cambiar_password=True,
        roles=["MECANICO"],
    )
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Password nueva de menos de 6 caracteres
            response = await client.post(
                "/auth/cambiar-password",
                json={
                    "password_actual": "PasswordValida123",
                    "password_nueva": "123",
                },
            )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_grupo_protegido_bloqueado_si_debe_cambiar_password_403():
    user_bloqueado = UsuarioActual(
        id=8,
        email="bloqueado@test.com",
        nombre="Usuario Bloqueado",
        activo=True,
        debe_cambiar_password=True,
        roles=["ADMIN"],
    )
    app.dependency_overrides[get_current_user] = lambda: user_bloqueado

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Intenta acceder a una ruta protegida
            response = await client.get("/eventos")
        assert response.status_code == 403
        assert "cambiar su contraseña" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
