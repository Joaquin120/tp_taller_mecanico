from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import bcrypt
from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.auth import requiere_password_actualizada
from app.core.config import get_settings
from app.core.database import crear_fabrica_sesiones, crear_motor
from app.modules.health.router import router as health_router
from app.modules.usuarios.router import router as auth_router
from app.modules.usuarios.router import router_protegido

_CONSTRAINT_MAP: dict[str, tuple[int, str]] = {
    "usuario_email_key": (
        status.HTTP_409_CONFLICT,
        "El correo ya se encuentra registrado",
    ),
    "ix_usuario_email": (
        status.HTTP_409_CONFLICT,
        "El correo ya se encuentra registrado",
    ),
    "uq_asignacion_rol_activa": (
        status.HTTP_409_CONFLICT,
        "El usuario ya posee ese rol vigente",
    ),
    "ck_asignacion_rol_rol_valido": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Rol inválido",
    ),
    "asignacion_rol_usuario_id_fkey": (
        status.HTTP_404_NOT_FOUND,
        "Usuario no encontrado",
    ),
    "asignacion_rol_otorgada_por_fkey": (
        status.HTTP_400_BAD_REQUEST,
        "El administrador otorgante no es válido",
    ),
}

_SQLSTATE_MAP: dict[str, tuple[int, str]] = {
    "23505": (status.HTTP_409_CONFLICT, "El recurso ya existe"),
    "23503": (status.HTTP_400_BAD_REQUEST, "Referencia inválida"),
    "23514": (status.HTTP_422_UNPROCESSABLE_CONTENT, "Valor inválido"),
    "23502": (status.HTTP_422_UNPROCESSABLE_CONTENT, "Campo obligatorio ausente"),
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    app.state.engine = crear_motor(
        database_url=settings.database_url,
        pool_size=settings.DATABASE_POOL_SIZE,
        echo=settings.SQL_ECHO,
    )
    app.state.session_factory = crear_fabrica_sesiones(app.state.engine)

    dummy_salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    app.state.dummy_hash = bcrypt.hashpw(
        b"timing_defense_dummy_pass",
        dummy_salt,
    ).decode("utf-8")

    yield

    await app.state.engine.dispose()


app = FastAPI(
    title="Taller Mecánico API",
    lifespan=lifespan,
)


@app.exception_handler(IntegrityError)
async def manejar_integrity_error(
    request: Request,
    exc: IntegrityError,
) -> JSONResponse:
    """Traduce violaciones de integridad sin filtrar detalles internos de PostgreSQL."""
    constraint = getattr(exc.orig, "constraint_name", None)
    if constraint in _CONSTRAINT_MAP:
        codigo, mensaje = _CONSTRAINT_MAP[constraint]
        return JSONResponse(status_code=codigo, content={"detail": mensaje})

    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    if sqlstate in _SQLSTATE_MAP:
        codigo, mensaje = _SQLSTATE_MAP[sqlstate]
        return JSONResponse(status_code=codigo, content={"detail": mensaje})

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "No se pudo completar la operación"},
    )


app.include_router(health_router)
app.include_router(auth_router, prefix="/auth")
app.include_router(
    router_protegido,
    dependencies=[Depends(requiere_password_actualizada)],
)
