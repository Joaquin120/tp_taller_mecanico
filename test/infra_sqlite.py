"""Infraestructura de pruebas de C-05 sobre una base SQLite en memoria.

Transparencia obligatoria (no afirmar falsamente "end-to-end"):

- ESTA BASE NO ES PostgreSQL. El entorno no tiene PostgreSQL ni Docker ni aiosqlite
  instalados, y ninguna instalación está autorizada todavía. Por eso las pruebas que
  usan este módulo ejecutan la lógica REAL (router, servicio, repositorio, Unit of
  Work, autenticación con cookie y bcrypt) sobre SQLite (stdlib) en memoria.
- La fachada `SesionFalsa` envuelve un `sqlalchemy.orm.Session` sincrónico y expige la
  misma superficie asincrónica que `AsyncSession` (`execute`, `flush`, `refresh`,
  `commit`, `rollback` síncrono `add`), emulando dos comportamientos de asyncpg:
  1. devolver `datetime` con zona horaria (SQLite devuelve `naive`), y
  2. un único `commit` por Unit of Work (`contador_commits` permite assertearlo).
- QUÉ NO CUBRE (requiere PostgreSQL, ver C-09):
  * los índices únicos PARCIALES `uq_asignacion_rol_activa`
    (`WHERE revocada_en IS NULL`), `uq_vehiculo_patente_activa`
    (`WHERE borrado_en IS NULL`) y `uq_repuesto_codigo_activo`
    (`WHERE borrado_en IS NULL`); SQLite los crea completos y más estrictos que
    producción, por eso se eliminan aquí;
  * los triggers PL/pgSQL de sólo agregado (`test/solo_agregado.sql`);
  * asyncpg como controlador, `alembic upgrade head`, `seed.py` y la suite `.http`.
- Nada de esto se instala ni configura: se usa exclusivamente el driver `sqlite3`
  que ya viene con Python.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from types import TracebackType
from typing import Any, Self

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

import app.modules.clientes.models  # noqa: F401  (registra las tablas en el metadata)
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401


def _normalizar_datetime(valor: Any) -> Any:
    """Devuelve el datetime en UTC aware, emulando a asyncpg con timestamptz."""
    if isinstance(valor, datetime) and valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor


def _normalizar_entidad(entidad: Any) -> Any:
    """Re-adjunta UTC a los datetime leídos de SQLite sin marcar la fila como sucia."""
    if isinstance(entidad, SQLModel):
        for nombre_columna in entidad.__table__.columns.keys():
            actual = entidad.__dict__.get(nombre_columna)
            if isinstance(actual, datetime) and actual.tzinfo is None:
                entidad.__dict__[nombre_columna] = actual.replace(tzinfo=timezone.utc)
        return entidad
    return _normalizar_datetime(entidad)


class _Escalares:
    """Proxy mínimo de `Result.scalars()` con los métodos que usan los repositorios."""

    def __init__(self, filas: list[tuple[Any, ...]]) -> None:
        self._filas = filas

    def all(self) -> list[Any]:
        return [fila[0] for fila in self._filas]

    def first(self) -> Any:
        return self._filas[0][0] if self._filas else None


class _Resultado:
    """Proxy mínimo de `Result` con `scalar_one`, `scalar_one_or_none` y `scalars()`."""

    def __init__(self, filas: list[tuple[Any, ...]]) -> None:
        self._filas = filas

    def scalar_one_or_none(self) -> Any:
        if not self._filas:
            return None
        if len(self._filas) > 1:
            raise RuntimeError("Se esperaba como máximo una fila")
        return self._filas[0][0]

    def scalar_one(self) -> Any:
        if len(self._filas) != 1:
            raise RuntimeError(f"Se esperaba exactamente una fila, hay {len(self._filas)}")
        return self._filas[0][0]

    def scalars(self) -> _Escalares:
        return _Escalares(self._filas)


class SesionFalsa:
    """Fachada asincrónica sobre un `sqlalchemy.orm.Session` de SQLite en memoria."""

    def __init__(self) -> None:
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)
        # SQLite crea este índice COMPLETO (sin WHERE), más estricto que PostgreSQL,
        # y rechazaría la reasignación de un rol vencido que en producción es válida.
        with self.engine.begin() as conn:
            conn.execute(text("DROP INDEX IF EXISTS uq_asignacion_rol_activa"))
            # `uq_repuesto_codigo_activo` también es parcial en PostgreSQL
            # (`WHERE borrado_en IS NULL`). SQLite lo crea completo y bloquearía
            # reutilizar el código de un repuesto dado de baja.
            conn.execute(text("DROP INDEX IF EXISTS uq_repuesto_codigo_activo"))
            # `uq_vehiculo_patente_activa` es parcial en PostgreSQL
            # (`WHERE borrado_en IS NULL`). SQLite lo crea completo y bloquearía
            # dar de alta un vehículo con la patente de uno dado de baja.
            conn.execute(text("DROP INDEX IF EXISTS uq_vehiculo_patente_activa"))
        self._sync = Session(self.engine, expire_on_commit=False, autoflush=False)
        self.contador_commits = 0

    # ---- superficie asincrónica requerida por repositorios y Unit of Work ----
    async def execute(self, stmt: Any) -> _Resultado:
        resultado = self._sync.execute(stmt)
        filas = [tuple(_normalizar_entidad(valor) for valor in fila) for fila in resultado.all()]
        return _Resultado(filas)

    def add(self, entidad: Any) -> None:
        # AsyncSession.add es síncrono en SQLAlchemy: los repositorios lo llaman sin await.
        self._sync.add(entidad)

    async def flush(self) -> None:
        self._sync.flush()

    async def refresh(self, entidad: Any) -> None:
        self._sync.refresh(entidad)
        _normalizar_entidad(entidad)

    async def delete(self, entidad: Any) -> None:
        self._sync.delete(entidad)

    async def commit(self) -> None:
        self.contador_commits += 1
        self._sync.commit()

    async def rollback(self) -> None:
        self._sync.rollback()

    # ---- utilidades de las pruebas ----
    def confirmar_siembra(self) -> None:
        """Confirma el sembrado de datos de prueba FUERA del UoW bajo prueba.

        Sin esto, el rollback del Unit of Work descartaría también las filas
        sembradas (la siembra y la operación compartirían la misma transacción).
        No incrementa `contador_commits`: ese contador mide los commits del UoW.
        """
        self._sync.commit()

    async def agregar_y_refrescar(self, entidad: Any) -> Any:
        """Agrega, refleja y refresca (patrón de BaseRepository.add) para sembrar datos."""
        self.add(entidad)
        await self.flush()
        await self.refresh(entidad)
        return entidad

    def contar(self, modelo: type[SQLModel]) -> int:
        """Cuenta filas reales de una tabla dentro de la transacción actual."""
        return len(list(self._sync.query(modelo).all()))

    def listar(self, modelo: type[SQLModel]) -> list[Any]:
        return list(self._sync.query(modelo).all())

    def cerrar(self) -> None:
        self._sync.close()
        self.engine.dispose()


class _ContextoSesion:
    """`async with fabrica() as sesion:` — no cierra la sesión (regla DD-06)."""

    def __init__(self, sesion: SesionFalsa) -> None:
        self._sesion = sesion

    async def __aenter__(self) -> SesionFalsa:
        return self._sesion

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return False


class FabricaSesiones:
    """Sustituto de `async_sessionmaker` para `app.state.session_factory`."""

    def __init__(self, sesion: SesionFalsa) -> None:
        self.sesion = sesion

    def __call__(self) -> _ContextoSesion:
        return _ContextoSesion(self.sesion)


def esquema_sqlite() -> Iterator[SesionFalsa]:
    """Crea una base en memoria nueva y libera sus recursos al terminar."""
    sesion = SesionFalsa()
    try:
        yield sesion
    finally:
        sesion.cerrar()


@contextmanager
def instalar_en_app(app: Any, sesion: SesionFalsa, dummy_hash: str) -> Iterator[None]:
    """Conecta la base simulada a la app real sin pisar overrides de otros tests."""
    estado_previo = getattr(app.state, "session_factory", None)
    dummy_previo = getattr(app.state, "dummy_hash", None)
    app.state.session_factory = FabricaSesiones(sesion)
    app.state.dummy_hash = dummy_hash
    try:
        yield
    finally:
        if estado_previo is None:
            if hasattr(app.state, "session_factory"):
                del app.state.session_factory
        else:
            app.state.session_factory = estado_previo
        if dummy_previo is None:
            if hasattr(app.state, "dummy_hash"):
                del app.state.dummy_hash
        else:
            app.state.dummy_hash = dummy_previo
