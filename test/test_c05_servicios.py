"""Pruebas C-05 con lógica REAL de `PersonalService` sobre SQLite en memoria.

Transparencia obligatoria (tarea 4 de las restricciones de esta corrida):

- Estas pruebas ejecutan el servicio REAL (`PersonalService.crear_usuario`,
  `asignar_rol`, `revocar_rol`), el Unit of Work REAL y los repositorios REALES.
  Ningún método de `PersonalService` está mockeado ni parcheado.
- La base NO es PostgreSQL: es SQLite (driver stdlib `sqlite3`) en memoria, sin
  instalar nada. Por eso NO es una prueba end-to-end de producción.
- QUÉ NO CUBRE (requiere PostgreSQL real, ver C-09):
  * el índice único PARCIAL `uq_asignacion_rol_activa` (aquí se elimina porque
    SQLite lo crea completo y más estricto que producción);
  * los triggers PL/pgSQL de sólo agregado (`test/solo_agregado.sql`);
  * asyncpg, `alembic upgrade head`, `seed.py` y la suite `.http`.

Cubre las brechas de las tareas 4.3, 4.5 y 5.2 de
`openspec/changes/authorization-rbac-protection/tasks.md`:
404 sin usuario, reasignación de rol vencido en un solo UoW, autoprotección
admin 409, último admin 409, eventos ALTA_USUARIO / ASIGNACION_ROL /
REVOCACION_ROL y rollback que no deja evento persistido.
"""

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core.auth import UsuarioActual
from app.core.security import hash_password
from test.infra_sqlite import SesionFalsa, esquema_sqlite
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, Usuario
from app.modules.usuarios.schemas import AsignarRolRequest, CrearUsuarioRequest
from app.modules.usuarios.service import (
    ACCION_ALTA_USUARIO,
    ACCION_ASIGNACION_ROL,
    ACCION_REVOCACION_ROL,
    PersonalService,
)
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_servicios_c05_1234567890123")
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


def actor_admin(usuario_id: int, email: str) -> UsuarioActual:
    """Administrador auténtico (UsuarioActual) para llamar al servicio real."""
    return UsuarioActual(
        id=usuario_id,
        email=email,
        nombre="Administrador",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
        roles_token=["ADMIN"],
    )


def acciones_auditadas(sesion: SesionFalsa) -> list[str]:
    return [evento.accion for evento in sesion.listar(EventoSeguridad)]


async def sembrar_usuario(sesion: SesionFalsa, email: str, nombre: str) -> Usuario:
    usuario = Usuario(
        email=email,
        nombre=nombre,
        password_hash="hash_fijo_de_prueba",
        activo=True,
        debe_cambiar_password=False,
    )
    usuario = await sesion.agregar_y_refrescar(usuario)
    return usuario


# -------------------------------------------------------------
# 4.3 — POST /usuarios/{id}/roles sin usuario -> 404 (servicio real)
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_asignar_rol_usuario_inexistente_responde_404(sesion: SesionFalsa):
    """El servicio real responde 404 cuando el usuario no existe (sin mocks)."""
    with pytest.raises(HTTPException) as exc_info:
        await PersonalService.asignar_rol(
            usuario_id=9999,
            dto=AsignarRolRequest(rol="MECANICO", vence_en=None),
            actor=actor_admin(1, "admin@test.com"),
            uow=UsuariosUnitOfWork(sesion),
        )

    assert exc_info.value.status_code == 404
    assert "Usuario no encontrado" in exc_info.value.detail
    # No se persistió ninguna asignación ni evento
    assert sesion.contar(AsignacionRol) == 0
    assert sesion.contar(EventoSeguridad) == 0
    assert sesion.contador_commits == 0


# -------------------------------------------------------------
# 4.3 — Reasignación de rol vencido: cierra anterior + alta nueva en un UoW
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_asignar_rol_vencido_cierra_anterior_e_inserta_nueva_en_un_solo_uow(
    sesion: SesionFalsa,
):
    """Reasigna un rol vencido: cierra la fila abierta vencida y da de alta la nueva
    dentro del MISMO Unit of Work (un único commit, regla DD-06)."""
    ahora = datetime.now(timezone.utc)
    usuario = await sembrar_usuario(sesion, "mecanico@test.com", "Mecánico")

    asignacion_vencida = AsignacionRol(
        usuario_id=usuario.id,
        rol="MECANICO",
        desde=ahora - timedelta(days=60),
        vence_en=ahora - timedelta(days=1),
    )
    asignacion_vencida = await sesion.agregar_y_refrescar(asignacion_vencida)
    id_vencida = asignacion_vencida.id
    sesion.confirmar_siembra()

    # Lógica real del servicio (sin mocks), con su propio UoW
    commits_antes = sesion.contador_commits
    nueva = await PersonalService.asignar_rol(
        usuario_id=usuario.id,
        dto=AsignarRolRequest(rol="MECANICO", vence_en=None),
        actor=actor_admin(1, "admin@test.com"),
        uow=UsuariosUnitOfWork(sesion),
    )
    commits_despues = sesion.contador_commits

    # 1. Un solo commit (el servicio abre y cierra UN UoW)
    assert commits_despues - commits_antes == 1

    # 2. La fila vencida quedó cerrada (revocada_en seteado)
    vencida_releida = next(f for f in sesion.listar(AsignacionRol) if f.id == id_vencida)
    assert vencida_releida.revocada_en is not None

    # 3. La nueva asignación quedó vigente (revocada_en None)
    assert nueva.revocada_en is None
    assert nueva.id != id_vencida

    # 4. Queda exactamente UNA asignación abierta de ese rol para ese usuario
    abiertas = [
        f for f in sesion.listar(AsignacionRol)
        if f.usuario_id == usuario.id and f.rol == "MECANICO" and f.revocada_en is None
    ]
    assert len(abiertas) == 1
    assert abiertas[0].id == nueva.id

    # 5. Se registró el evento ASIGNACION_ROL (auditoría real)
    assert ACCION_ASIGNACION_ROL in acciones_auditadas(sesion)


# -------------------------------------------------------------
# 5.2 — Evento ALTA_USUARIO al crear usuario
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_crear_usuario_registra_evento_alta_usuario(sesion: SesionFalsa):
    """`crear_usuario` real genera el evento ALTA_USUARIO y deja al usuario con
    contraseña provisoria (debe_cambiar_password=True) y su rol vigente."""
    actor = actor_admin(1, "admin@test.com")

    usuario, roles = await PersonalService.crear_usuario(
        dto=CrearUsuarioRequest(
            email="recepcion@test.com",
            nombre="Recepción",
            password="Provisoria123",
            rol="RECEPCION",
        ),
        actor=actor,
        uow=UsuariosUnitOfWork(sesion),
    )

    # Evento de auditoría real
    assert ACCION_ALTA_USUARIO in acciones_auditadas(sesion)

    # El usuario existe, está activo y debe cambiar la contraseña provisoria
    assert usuario.id is not None
    assert usuario.activo is True
    assert usuario.debe_cambiar_password is True
    assert roles == ["RECEPCION"]

    # Tiene la asignación de rol vigente
    asignaciones = sesion.listar(AsignacionRol)
    assert len(asignaciones) == 1
    assert asignaciones[0].usuario_id == usuario.id
    assert asignaciones[0].rol == "RECEPCION"
    assert asignaciones[0].revocada_en is None


# -------------------------------------------------------------
# 5.2 — Evento ASIGNACION_ROL
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_asignar_rol_registra_evento_asignacion_rol(sesion: SesionFalsa):
    """Asignar un rol por primera vez genera el evento ASIGNACION_ROL real."""
    usuario = await sembrar_usuario(sesion, "mecanico@test.com", "Mecánico")

    await PersonalService.asignar_rol(
        usuario_id=usuario.id,
        dto=AsignarRolRequest(rol="MECANICO", vence_en=None),
        actor=actor_admin(1, "admin@test.com"),
        uow=UsuariosUnitOfWork(sesion),
    )

    assert acciones_auditadas(sesion) == [ACCION_ASIGNACION_ROL]


# -------------------------------------------------------------
# 5.2 — Evento REVOCACION_ROL
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_revocar_rol_registra_evento_revocacion_rol(sesion: SesionFalsa):
    """Revocar un rol real genera el evento REVOCACION_ROL y cierra la fila."""
    ahora = datetime.now(timezone.utc)
    usuario = await sembrar_usuario(sesion, "mecanico@test.com", "Mecánico")
    asignacion = AsignacionRol(usuario_id=usuario.id, rol="MECANICO", desde=ahora)
    asignacion = await sesion.agregar_y_refrescar(asignacion)
    sesion.confirmar_siembra()

    revocada = await PersonalService.revocar_rol(
        usuario_id=usuario.id,
        rol="MECANICO",
        actor=actor_admin(1, "admin@test.com"),
        uow=UsuariosUnitOfWork(sesion),
    )

    assert ACCION_REVOCACION_ROL in acciones_auditadas(sesion)
    assert revocada.revocada_en is not None
    assert revocada.id == asignacion.id


# -------------------------------------------------------------
# 4.5 / RN-05 — Autoprotección: el admin no se revoca su ADMIN -> 409
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_revocar_rol_autoproteccion_admin_responde_409(sesion: SesionFalsa):
    """Un administrador no puede revocarse su propio ADMIN (RN-05): 409, y no
    se escribe nada (sin commit, sin evento, la asignación sigue abierta)."""
    ahora = datetime.now(timezone.utc)
    admin = await sembrar_usuario(sesion, "admin@test.com", "Admin")
    asignacion = AsignacionRol(usuario_id=admin.id, rol="ADMIN", desde=ahora)
    await sesion.agregar_y_refrescar(asignacion)
    sesion.confirmar_siembra()

    eventos_antes = len(acciones_auditadas(sesion))
    commits_antes = sesion.contador_commits

    with pytest.raises(HTTPException) as exc_info:
        await PersonalService.revocar_rol(
            usuario_id=admin.id,
            rol="ADMIN",
            actor=actor_admin(admin.id, "admin@test.com"),
            uow=UsuariosUnitOfWork(sesion),
        )

    assert exc_info.value.status_code == 409
    assert "no puede revocar su propio rol ADMIN" in exc_info.value.detail

    # Nada quedó persistido
    assert sesion.contador_commits - commits_antes == 0
    assert len(acciones_auditadas(sesion)) - eventos_antes == 0
    relectura = sesion.listar(AsignacionRol)[0]
    assert relectura.revocada_en is None


# -------------------------------------------------------------
# 4.5 / RN-05 — Último administrador vigente -> 409
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_revocar_rol_ultimo_admin_vigente_responde_409(sesion: SesionFalsa):
    """Revocar al último ADMIN vigente deja al sistema sin administradores: 409.

    Nota de alcance (auto-cobertura documentada): vía API este caso es
    inalcanzable cuando el actor es OTRO ADMIN vigente, porque el propio ADMIN
    del actor siempre suma en el conteo de admins vigentes. Por eso el actor es
    un `UsuarioActual` sintético que representa a un administrador cuyo rol ya
    no está vigente en la base. Es una prueba de LÓGICA DE SERVICIO, no un
    flujo HTTP end-to-end.
    """
    ahora = datetime.now(timezone.utc)
    admin = await sembrar_usuario(sesion, "admin@test.com", "Admin")
    asignacion = AsignacionRol(usuario_id=admin.id, rol="ADMIN", desde=ahora)
    await sesion.agregar_y_refrescar(asignacion)
    sesion.confirmar_siembra()

    # Actor sintético: su ADMIN no está vigente en la base de datos
    actor_administrador_destituido = actor_admin(999, "destituido@test.com")

    commits_antes = sesion.contador_commits

    with pytest.raises(HTTPException) as exc_info:
        await PersonalService.revocar_rol(
            usuario_id=admin.id,
            rol="ADMIN",
            actor=actor_administrador_destituido,
            uow=UsuariosUnitOfWork(sesion),
        )

    assert exc_info.value.status_code == 409
    assert "sin administradores vigentes" in exc_info.value.detail
    assert sesion.contador_commits - commits_antes == 0
    assert sesion.listar(AsignacionRol)[0].revocada_en is None


# -------------------------------------------------------------
# 5.2 — Un rollback no deja persistido el evento
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_rollback_no_deja_evento_persistido(sesion: SesionFalsa):
    """Si la escritura del evento falla dentro del UoW, el rollback descarta
    TAMBIÉN el alta de usuario y la asignación de rol: cero eventos, cero filas.

    Se fuerza el fallo con un trigger SQLite `RAISE(ABORT)` sobre
    `evento_seguridad` (emulando los triggers de sólo agregado de PostgreSQL).
    Este trigger es específico de la base simulada; NO reproduce los triggers
    PL/pgSQL reales, que requieren PostgreSQL.
    """
    with sesion.engine.begin() as conn:
        conn.execute(text(
            "CREATE TRIGGER trg_solo_agregado BEFORE INSERT ON evento_seguridad "
            "BEGIN SELECT RAISE(ABORT, 'tabla de solo agregado'); END"
        ))

    eventos_antes = len(acciones_auditadas(sesion))
    asignaciones_antes = sesion.contar(AsignacionRol)
    usuarios_antes = sesion.contar(Usuario)
    commits_antes = sesion.contador_commits

    with pytest.raises(Exception):
        await PersonalService.crear_usuario(
            dto=CrearUsuarioRequest(
                email="nuevo@test.com",
                nombre="Nuevo",
                password="Secreta123",
                rol="RECEPCION",
            ),
            actor=actor_admin(1, "admin@test.com"),
            uow=UsuariosUnitOfWork(sesion),
        )

    # El evento NO quedó persistido
    assert len(acciones_auditadas(sesion)) - eventos_antes == 0
    # Y el rollback descartó también usuario y asignación (sin escrituras parciales)
    assert sesion.contar(AsignacionRol) - asignaciones_antes == 0
    assert sesion.contar(Usuario) - usuarios_antes == 0
    assert sesion.contador_commits - commits_antes == 0
