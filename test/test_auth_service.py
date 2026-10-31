import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401
from app.modules.usuarios.repository import IntentoAccesoRepository
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
import pytest

from app.core.security import hash_password
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import IntentoAcceso, Usuario
from app.modules.usuarios.schemas import RegistroClienteRequest
from app.modules.usuarios.service import AuthService
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_for_auth_service_1234")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")


@pytest.mark.asyncio
async def test_registrar_cliente_exitoso():
    session = AsyncMock()
    uow = UsuariosUnitOfWork(session)

    # Mock repos
    uow.usuarios.get_by_email = AsyncMock(return_value=None)
    uow.clientes.get_by_documento = AsyncMock(return_value=None)

    async def mock_add_usr(u):
        u.id = 100
        return u

    async def mock_add_rol(r):
        r.id = 200
        return r

    async def mock_add_cli(c):
        c.id = 300
        return c

    uow.usuarios.add = AsyncMock(side_effect=mock_add_usr)
    uow.roles.add = AsyncMock(side_effect=mock_add_rol)
    uow.clientes.add = AsyncMock(side_effect=mock_add_cli)

    dto = RegistroClienteRequest(
        email="nuevo@cliente.com",
        password="PasswordSeguro123",
        nombre="Juan Perez",
        documento="30123456",
        telefono="1122334455",
    )

    usuario, roles, cliente_id = await AuthService.registrar_cliente(dto, uow)

    assert usuario.id == 100
    assert usuario.email == "nuevo@cliente.com"
    assert usuario.nombre == "Juan Perez"
    assert usuario.password_hash != "PasswordSeguro123"
    assert roles == ["CLIENTE"]
    assert cliente_id == 300

    uow.usuarios.add.assert_awaited_once()
    uow.roles.add.assert_awaited_once()
    uow.clientes.add.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_registrar_cliente_email_duplicado_lanza_409():
    session = AsyncMock()
    uow = UsuariosUnitOfWork(session)

    usuario_existente = Usuario(
        id=1,
        email="duplicado@cliente.com",
        nombre="Existente",
        password_hash="hash",
    )
    uow.usuarios.get_by_email = AsyncMock(return_value=usuario_existente)
    uow.clientes.get_by_documento = AsyncMock(return_value=None)

    dto = RegistroClienteRequest(
        email="duplicado@cliente.com",
        password="Password123",
        nombre="Juan",
        documento="12345678",
        telefono="123456",
    )

    with pytest.raises(HTTPException) as exc_info:
        await AuthService.registrar_cliente(dto, uow)

    assert exc_info.value.status_code == 409
    assert "correo ya se encuentra registrado" in exc_info.value.detail
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_registrar_cliente_documento_duplicado_lanza_409():
    session = AsyncMock()
    uow = UsuariosUnitOfWork(session)

    cliente_existente = Cliente(
        id=1,
        nombre="Otro Cliente",
        documento="30123456",
        telefono="9999",
    )
    uow.usuarios.get_by_email = AsyncMock(return_value=None)
    uow.clientes.get_by_documento = AsyncMock(return_value=cliente_existente)

    dto = RegistroClienteRequest(
        email="nuevo_email@cliente.com",
        password="Password123",
        nombre="Juan",
        documento="30123456",
        telefono="123456",
    )

    with pytest.raises(HTTPException) as exc_info:
        await AuthService.registrar_cliente(dto, uow)

    assert exc_info.value.status_code == 409
    assert "documento ya pertenece" in exc_info.value.detail
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_exitoso():
    pwd = "MiPasswordValido"
    pwd_hash = await hash_password(pwd)
    usuario = Usuario(
        id=1,
        email="login@test.com",
        nombre="Tester",
        password_hash=pwd_hash,
        activo=True,
    )

    def make_session(fallos: int = 0, usr: Usuario | None = usuario, roles: list[str] = ["CLIENTE"]):
        session = AsyncMock()
        # mock execute for contar_fallos_recientes
        mock_exito = MagicMock()
        mock_exito.scalar_one_or_none.return_value = None
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = fallos

        mock_usr = MagicMock()
        mock_usr.scalar_one_or_none.return_value = usr

        mock_roles = MagicMock()
        mock_roles.scalars.return_value.all.return_value = roles

        session.execute.side_effect = [
            mock_exito,
            mock_count,  # 1ra session: rate limit
            mock_usr,
            mock_roles,  # 2da session: auth
        ]
        return session

    # Session 1: rate limit
    session_rl = AsyncMock()
    res_exito = MagicMock()
    res_exito.scalar_one_or_none.return_value = None
    res_fallos = MagicMock()
    res_fallos.scalar_one.return_value = 0
    session_rl.execute.side_effect = [res_exito, res_fallos]

    # Session 2: lookup
    session_auth = AsyncMock()
    res_usr = MagicMock()
    res_usr.scalar_one_or_none.return_value = usuario
    res_roles = MagicMock()
    res_roles.scalars.return_value.all.return_value = ["CLIENTE"]
    session_auth.execute.side_effect = [res_usr, res_roles]

    # Session 3: audit intento
    session_audit = AsyncMock()

    sessions = [session_rl, session_auth, session_audit]

    class FakeSessionFactory:
        def __call__(self):
            s = sessions.pop(0)
            ctx = AsyncMock()
            ctx.__aenter__.return_value = s
            ctx.__aexit__.return_value = None
            return ctx

    user_res, token, roles_res = await AuthService.login(
        email="login@test.com",
        password=pwd,
        ip="127.0.0.1",
        app_state_or_dummy_hash="dummy_hash_str",
        session_factory=FakeSessionFactory(),
    )

    assert user_res.id == 1
    assert user_res.email == "login@test.com"
    assert roles_res == ["CLIENTE"]
    assert isinstance(token, str)
    session_audit.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_credenciales_incorrectas_lanza_401():
    pwd_hash = await hash_password("PasswordReal")
    usuario = Usuario(
        id=2,
        email="login_fail@test.com",
        nombre="Tester",
        password_hash=pwd_hash,
        activo=True,
    )

    session_rl = AsyncMock()
    res_exito = MagicMock()
    res_exito.scalar_one_or_none.return_value = None
    res_fallos = MagicMock()
    res_fallos.scalar_one.return_value = 0
    session_rl.execute.side_effect = [res_exito, res_fallos]

    session_auth = AsyncMock()
    res_usr = MagicMock()
    res_usr.scalar_one_or_none.return_value = usuario
    session_auth.execute.side_effect = [res_usr]

    session_audit = AsyncMock()
    sessions = [session_rl, session_auth, session_audit]

    class FakeSessionFactory:
        def __call__(self):
            s = sessions.pop(0)
            ctx = AsyncMock()
            ctx.__aenter__.return_value = s
            ctx.__aexit__.return_value = None
            return ctx

    with pytest.raises(HTTPException) as exc_info:
        await AuthService.login(
            email="login_fail@test.com",
            password="PasswordEquivocado",
            ip="127.0.0.1",
            app_state_or_dummy_hash="dummy_hash_str",
            session_factory=FakeSessionFactory(),
        )

    assert exc_info.value.status_code == 401
    assert "inválidas" in exc_info.value.detail.lower()
    session_audit.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_usuario_inexistente_usa_dummy_hash_y_lanza_401():
    dummy_hash = await hash_password("dummy_pass")

    session_rl = AsyncMock()
    res_exito = MagicMock()
    res_exito.scalar_one_or_none.return_value = None
    res_fallos = MagicMock()
    res_fallos.scalar_one.return_value = 0
    session_rl.execute.side_effect = [res_exito, res_fallos]

    session_auth = AsyncMock()
    res_usr = MagicMock()
    res_usr.scalar_one_or_none.return_value = None
    session_auth.execute.side_effect = [res_usr]

    session_audit = AsyncMock()
    sessions = [session_rl, session_auth, session_audit]

    class FakeSessionFactory:
        def __call__(self):
            s = sessions.pop(0)
            ctx = AsyncMock()
            ctx.__aenter__.return_value = s
            ctx.__aexit__.return_value = None
            return ctx

    with pytest.raises(HTTPException) as exc_info:
        await AuthService.login(
            email="no_existe@test.com",
            password="CualquierPassword",
            ip="10.0.0.1",
            app_state_or_dummy_hash=dummy_hash,
            session_factory=FakeSessionFactory(),
        )

    assert exc_info.value.status_code == 401
    assert "inválidas" in exc_info.value.detail.lower()
    session_audit.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_rate_limit_5_fallos_lanza_429():
    session_rl = AsyncMock()
    res_exito = MagicMock()
    res_exito.scalar_one_or_none.return_value = None
    res_fallos = MagicMock()
    res_fallos.scalar_one.return_value = 5  # 5 fallos acumulados
    session_rl.execute.side_effect = [res_exito, res_fallos]

    class FakeSessionFactory:
        def __call__(self):
            ctx = AsyncMock()
            ctx.__aenter__.return_value = session_rl
            ctx.__aexit__.return_value = None
            return ctx

    with pytest.raises(HTTPException) as exc_info:
        await AuthService.login(
            email="bloqueado@test.com",
            password="CualquierPassword",
            ip="127.0.0.1",
            app_state_or_dummy_hash="dummy",
            session_factory=FakeSessionFactory(),
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers.get("Retry-After") == "60"
    assert "intentos" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_intento_acceso_repositorio_login_exitoso_reinicia_conteo():
    session = AsyncMock()
    repo = IntentoAccesoRepository(session)

    # Simular que hay un éxito reciente
    ultimo_exito = datetime.now(timezone.utc)
    mock_res_exito = MagicMock()
    mock_res_exito.scalar_one_or_none.return_value = ultimo_exito

    mock_res_fallos = MagicMock()
    mock_res_fallos.scalar_one.return_value = 0  # posteriores al éxito son 0

    session.execute.side_effect = [mock_res_exito, mock_res_fallos]

    conteo = await repo.contar_fallos_recientes("user@test.com", "1.1.1.1", ventana_segundos=60)
    assert conteo == 0
