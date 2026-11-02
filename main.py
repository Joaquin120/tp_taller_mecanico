from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import bcrypt
from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.auth import requiere_password_actualizada
from app.core.config import get_settings
from app.core.database import crear_fabrica_sesiones, crear_motor
from app.modules.clientes.router import router_protegido as clientes_router_protegido
from app.modules.health.router import router as health_router
from app.modules.ordenes.router import router_protegido as ordenes_router_protegido
from app.modules.repuestos.router import router as repuestos_router
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
    "uq_repuesto_codigo_activo": (
        status.HTTP_409_CONFLICT,
        "El código de repuesto ya se encuentra registrado",
    ),
    "ck_repuesto_precio_positivo": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "El precio debe ser mayor a cero",
    ),
    "ck_repuesto_stock_no_negativo": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "El stock no puede ser negativo",
    ),
    "ck_movimiento_stock_cantidad_no_cero": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "La cantidad del movimiento no puede ser cero",
    ),
    "ck_historial_precio_nuevo_positivo": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "El precio nuevo debe ser mayor a cero",
    ),
    "ck_historial_precio_cambio_requerido": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "El precio nuevo debe ser distinto del anterior",
    ),
    "cliente_documento_key": (
        status.HTTP_409_CONFLICT,
        "Ya existe un cliente registrado con ese documento",
    ),
    "ix_cliente_documento": (
        status.HTTP_409_CONFLICT,
        "Ya existe un cliente registrado con ese documento",
    ),
    "uq_vehiculo_patente_activa": (
        status.HTTP_409_CONFLICT,
        "Ya existe un vehículo vigente registrado con esa patente",
    ),
    "ck_vehiculo_anio_valido": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Año de vehículo inválido",
    ),
    "vehiculo_cliente_id_fkey": (
        status.HTTP_404_NOT_FOUND,
        "Cliente no encontrado",
    ),
    "uq_item_orden_orden_repuesto": (
        status.HTTP_409_CONFLICT,
        "El repuesto ya forma parte de la orden",
    ),
    "ck_item_orden_cantidad_positiva": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "La cantidad del ítem debe ser mayor a cero",
    ),
    "ck_item_orden_precio_positivo": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "El precio unitario debe ser mayor a cero",
    ),
    "ck_orden_trabajo_total_no_negativo": (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "El total de la orden no puede ser negativo",
    ),
    "orden_trabajo_vehiculo_id_fkey": (
        status.HTTP_404_NOT_FOUND,
        "Vehículo no encontrado",
    ),
    "orden_trabajo_mecanico_id_fkey": (
        status.HTTP_400_BAD_REQUEST,
        "Mecánico no válido",
    ),
    "item_orden_orden_id_fkey": (
        status.HTTP_404_NOT_FOUND,
        "Orden de trabajo no encontrada",
    ),
    "item_orden_repuesto_id_fkey": (
        status.HTTP_400_BAD_REQUEST,
        "Repuesto no válido",
    ),
    "movimiento_stock_orden_id_fkey": (
        status.HTTP_404_NOT_FOUND,
        "Orden de trabajo no encontrada",
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
app.include_router(
    clientes_router_protegido,
    dependencies=[Depends(requiere_password_actualizada)],
)
app.include_router(
    ordenes_router_protegido,
    dependencies=[Depends(requiere_password_actualizada)],
)
app.include_router(
    repuestos_router,
    dependencies=[Depends(requiere_password_actualizada)],
)
