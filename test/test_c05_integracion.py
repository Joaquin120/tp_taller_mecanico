"""Pruebas de integración C-05 con cookies reales sobre SQLite en memoria.

Transparencia obligatoria (no afirmar falsamente "end-to-end"):

- ESTA BASE NO ES PostgreSQL. El entorno no tiene PostgreSQL ni Docker ni
  aiosqlite instalados, y ninguna instalación está autorizada. Estas pruebas
  ejecutan la lógica REAL (router, servicio, repositorio, Unit of Work,
  autenticación con cookie y bcrypt) sobre SQLite (stdlib) en memoria.
- NO SE MOCKEA NADA de la lógica que se verifica: ni `get_current_user`, ni
  `require_roles`, ni `requiere_password_actualizada`, ni `AuthService`, ni
  `PersonalService`. Las cookies viajan por HTTP real (httpx + ASGITransport).
- QUÉ NO CUBRE (requiere PostgreSQL real, ver C-09):
  * el índice único parcial `uq_asignacion_rol_activa`;
  * los triggers PL/pgSQL de sólo agregado (`test/solo_agregado.sql`);
  * asyncpg, `alembic upgrade head`, `seed.py` y la suite `.http`.

Cubre las brechas de las tareas 2.4 (cambio de contraseña con cookie anterior
401 y cookie nueva 200) y RN-04 / caso C-07 (misma cookie tras revocación ->
403 y `/auth/yo` refleja el estado), y el 404 de `POST /usuarios/{id}/roles`
sin usuario (tarea 4.3) con el servicio real.
"""

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import hash_password
from test.infra_sqlite import SesionFalsa, esquema_sqlite, instalar_en_app
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, Usuario
from app.modules.usuarios.service import ACCION_CAMBIO_PASSWORD
from main import app


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_integracion_c05_12345678901")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")


@pytest.fixture
async def sesion():
    """Base SQLite en memoria nueva por prueba, liberada al terminar."""
    gen = esquema_sqlite()
    base: SesionFalsa = next(gen)
    try:
        yield base
    finally:
        gen.close()


@pytest.fixture
async def base_instalada(sesion: SesionFalsa):
    """Conecta la base simulada a la app real (sin mocks de autenticación)."""
    dummy_hash = await hash_password("timing_defense_dummy_pass")
    with instalar_en_app(app, sesion, dummy_hash):
        yield sesion


def _extraer_cookie(response) -> str:
    """Extrae el valor crudo de la cookie access_token desde el header Set-Cookie."""
    for set_cookie in response.headers.get_list("set-cookie"):
        if set_cookie.startswith("access_token="):
            return set_cookie.split(";", 1)[0].split("=", 1)[1]
    raise AssertionError("La respuesta no incluyó la cookie access_token")


def _cliente_con_cookie(token: str) -> AsyncClient:
    """Cliente HTTP con UNA cookie explícita y sin cookie-jar (misma cookie exacta)."""
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Cookie": f"access_token={token}"},
    )


def _cliente_anonimo() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _sembrar_admin(
    sesion: SesionFalsa,
    email: str,
    password: str,
    *,
    debe_cambiar_password: bool = False,
) -> tuple[Usuario, str]:
    """Siembra un administrador con hash bcrypt REAL y devuelve (usuario, password)."""
    pwd_hash = await hash_password(password)
    usuario = Usuario(
        email=email,
        nombre=f"Admin {email}",
        password_hash=pwd_hash,
        activo=True,
        debe_cambiar_password=debe_cambiar_password,
    )
    usuario = await sesion.agregar_y_refrescar(usuario)
    asignacion = AsignacionRol(usuario_id=usuario.id, rol="ADMIN")
    await sesion.agregar_y_refrescar(asignacion)
    return usuario, password


async def _login(email: str, password: str) -> str:
    """Realiza un login REAL (bcrypt, rate-limit y cookie) y devuelve el token."""
    async with _cliente_anonimo() as client:
        response = await client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
    assert response.status_code == 200, response.text
    return _extraer_cookie(response)


# -------------------------------------------------------------
# Tarea 2.4 / caso C-09 — Cambio de contraseña: cookie anterior 401, nueva 200
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_cambio_password_invalida_cookie_anterior_y_acepta_nueva(
    base_instalada: SesionFalsa,
):
    """Flujo REAL completo (login -> cambio -> verificación de cookies), sin mocks.

    1. Login real de un admin con contraseña provisoria (bcrypt real).
    2. Con la cookie del login, el grupo protegido responde 403 (RN-06).
    3. Cambio real de contraseña -> se emite una cookie nueva.
    4. La cookie ANTERIOR exacta responde 401 en una ruta protegida (RN-07).
    5. La cookie NUEVA responde 200 en la misma ruta protegida, sin esperar.
    """
    usuario, password_provisoria = await _sembrar_admin(
        base_instalada, "admin_cambio@test.com", "Provisoria123",
        debe_cambiar_password=True,
    )

    # 1. Login real (bcrypt + rate-limit + cookie HttpOnly)
    cookie_anterior = await _login("admin_cambio@test.com", password_provisoria)

    # 2. Grupo protegido bloqueado mientras deba cambiar la contraseña (RN-06)
    async with _cliente_con_cookie(cookie_anterior) as client:
        bloqueada = await client.get("/eventos")
    assert bloqueada.status_code == 403
    assert "debe cambiar" in bloqueada.json()["detail"].lower()

    # 3. Cambio real de contraseña con la cookie del login
    async with _cliente_con_cookie(cookie_anterior) as client:
        cambio = await client.post(
            "/auth/cambiar-password",
            json={
                "password_actual": password_provisoria,
                "password_nueva": "NuevaClaveSegura123",
            },
        )
    assert cambio.status_code == 200, cambio.text
    cookie_nueva = _extraer_cookie(cambio)
    assert cookie_nueva != cookie_anterior, "El cambio debe emitir un token distinto"

    # 4. La cookie ANTERIOR exacta queda invalidada (RN-07), sin esperar
    async with _cliente_con_cookie(cookie_anterior) as client:
        con_anterior = await client.get("/eventos")
    assert con_anterior.status_code == 401
    assert "invalidada" in con_anterior.json()["detail"].lower()

    # 5. La cookie NUEVA abre el grupo protegido inmediatamente
    async with _cliente_con_cookie(cookie_nueva) as client:
        con_nueva = await client.get("/eventos")
    assert con_nueva.status_code == 200, con_nueva.text
    # La ruta protegida responde y muestra el evento del propio cambio (auditoría real)
    assert any(
        item["accion"] == ACCION_CAMBIO_PASSWORD
        for item in con_nueva.json()["items"]
    )

    # Auditoría real del cambio (evento CAMBIO_PASSWORD)
    eventos = base_instalada.listar(EventoSeguridad)
    assert [e.accion for e in eventos].count(ACCION_CAMBIO_PASSWORD) == 1


# -------------------------------------------------------------
# RN-04 / caso C-07 — Revocación efectiva con la MISMA cookie -> 403
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_revocacion_rol_surte_efecto_inmediato_con_misma_cookie(
    base_instalada: SesionFalsa,
):
    """Flujo REAL completo (dos administradores, revocación y verificación), sin mocks.

    1. Login real de dos administradores (A y B), ambos con ADMIN vigente.
    2. Con la cookie de A, una ruta protegida responde 200 (tiene ADMIN).
    3. B revoca el ADMIN de A (petición real con la cookie de B).
    4. Con EXACTAMENTE la misma cookie de A, la misma ruta protegida responde 403.
    5. `/auth/yo` con la cookie de A refleja el estado: roles de BD vacíos
       frente al token que todavía declara ADMIN.
    """
    admin_a, password_a = await _sembrar_admin(base_instalada, "admin_a@test.com", "ClaveAdminA1")
    admin_b, password_b = await _sembrar_admin(base_instalada, "admin_b@test.com", "ClaveAdminB1")

    cookie_a = await _login("admin_a@test.com", password_a)
    cookie_b = await _login("admin_b@test.com", password_b)

    # 1. Antes de la revocación, A accede a una ruta protegida que exige ADMIN
    async with _cliente_con_cookie(cookie_a) as client:
        antes = await client.get("/eventos")
    assert antes.status_code == 200, antes.text

    # 2. B revoca el ADMIN de A (servicio real, sin mocks)
    async with _cliente_con_cookie(cookie_b) as client:
        revocacion = await client.delete(f"/usuarios/{admin_a.id}/roles/ADMIN")
    assert revocacion.status_code == 200, revocacion.text

    # 3. EXACTAMENTE la misma cookie de A -> 403 en la petición siguiente (RN-04)
    async with _cliente_con_cookie(cookie_a) as client:
        despues = await client.get("/eventos")
    assert despues.status_code == 403
    assert "permisos" in despues.json()["detail"].lower()

    # 4. /auth/yo refleja la diferencia: roles vigentes de BD vacíos,
    #    roles del token todavía ["ADMIN"]
    async with _cliente_con_cookie(cookie_a) as client:
        yo = await client.get("/auth/yo")
    assert yo.status_code == 200, yo.text
    datos = yo.json()
    assert datos["roles"] == []
    assert datos["roles_token"] == ["ADMIN"]
    assert datos["id"] == admin_a.id


# -------------------------------------------------------------
# Tarea 4.3 — POST /usuarios/{id}/roles responde 404 sin usuario (servicio real)
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_roles_usuario_inexistente_responde_404(
    base_instalada: SesionFalsa,
):
    """El endpoint real responde 404 cuando el usuario no existe, sin mocks.

    El router, el servicio `PersonalService.asignar_rol` real, el Unit of Work y
    los repositorios se ejecutan de verdad; sólo la base es SQLite simulada.
    """
    await _sembrar_admin(base_instalada, "admin@test.com", "ClaveAdmin123")
    cookie = await _login("admin@test.com", "ClaveAdmin123")

    async with _cliente_con_cookie(cookie) as client:
        respuesta = await client.post(
            "/usuarios/9999/roles",
            json={"rol": "MECANICO", "vence_en": None},
        )

    assert respuesta.status_code == 404
    assert "Usuario no encontrado" in respuesta.json()["detail"]

    # No se persistió ninguna asignación ni evento
    assert base_instalada.contar(AsignacionRol) == 1  # sólo la del admin sembrado
    assert base_instalada.contar(EventoSeguridad) == 0
