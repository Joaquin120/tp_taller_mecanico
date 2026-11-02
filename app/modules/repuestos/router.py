"""Router del catálogo de repuestos.

RBAC (matriz de la KB):
- lectura (`GET /repuestos`, `GET /repuestos/{id}`): ADMIN, RECEPCION, MECANICO.
- mutaciones e historiales: sólo ADMIN.
"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UsuarioActual, requiere_rol
from app.core.database import get_session
from app.core.paginacion import PaginatedResponse, ParamsPaginacion
from app.modules.repuestos.schemas import (
    HistorialPrecioResponse,
    MovimientoStockResponse,
    ReponerStockRequest,
    RepuestoCreate,
    RepuestoResponse,
    RepuestoUpdate,
)
from app.modules.repuestos.service import CatalogoService
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork

ROLES_LECTURA = ("ADMIN", "RECEPCION", "MECANICO")

router = APIRouter(prefix="/repuestos", tags=["repuestos"])


async def get_repuestos_uow(
    session: AsyncSession = Depends(get_session),
) -> RepuestosUnitOfWork:
    return RepuestosUnitOfWork(session)


@router.get(
    "",
    response_model=PaginatedResponse[RepuestoResponse],
    status_code=status.HTTP_200_OK,
    summary="Listado paginado de repuestos",
)
async def listar_repuestos(
    params: ParamsPaginacion = Depends(),
    q: str | None = Query(default=None, max_length=255, description="Búsqueda por descripción"),
    actor: UsuarioActual = Depends(requiere_rol(*ROLES_LECTURA)),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> PaginatedResponse[RepuestoResponse]:
    """Devuelve repuestos vigentes con búsqueda parcial por descripción."""
    return await CatalogoService.listar(q, params.page, params.size, uow)


@router.post(
    "",
    response_model=RepuestoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de repuesto con stock inicial",
)
async def crear_repuesto(
    payload: RepuestoCreate,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> RepuestoResponse:
    """Crea el repuesto y su movimiento de alta cuando el stock inicial es positivo."""
    return await CatalogoService.crear(payload, actor, uow)


@router.get(
    "/{id}",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
    summary="Detalle de un repuesto vigente",
)
async def obtener_repuesto(
    id: int,
    actor: UsuarioActual = Depends(requiere_rol(*ROLES_LECTURA)),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> RepuestoResponse:
    """Devuelve el repuesto vigente o 404."""
    return await CatalogoService.obtener(id, uow)


@router.patch(
    "/{id}",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
    summary="Actualización de descripción y precio",
)
async def actualizar_repuesto(
    id: int,
    payload: RepuestoUpdate,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> RepuestoResponse:
    """Actualiza descripción y/o precio; el historial se registra si el precio cambia."""
    return await CatalogoService.actualizar(id, payload, actor, uow)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Baja lógica de un repuesto",
)
async def eliminar_repuesto(
    id: int,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> Response:
    """Aplica borrado lógico sin eliminar la fila."""
    await CatalogoService.dar_de_baja(id, uow)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{id}/reponer",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
    summary="Reposición de stock",
)
async def reponer_stock(
    id: int,
    payload: ReponerStockRequest,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> RepuestoResponse:
    """Incrementa el stock y registra el movimiento de reposición."""
    return await CatalogoService.reponer(id, payload, actor, uow)


@router.get(
    "/{id}/movimientos",
    response_model=PaginatedResponse[MovimientoStockResponse],
    status_code=status.HTTP_200_OK,
    summary="Historial de movimientos de stock",
)
async def listar_movimientos(
    id: int,
    params: ParamsPaginacion = Depends(),
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> PaginatedResponse[MovimientoStockResponse]:
    """Historial de sólo lectura, del movimiento más reciente al más antiguo."""
    return await CatalogoService.listar_movimientos(id, params.page, params.size, uow)


@router.get(
    "/{id}/precios",
    response_model=PaginatedResponse[HistorialPrecioResponse],
    status_code=status.HTTP_200_OK,
    summary="Historial de precios",
)
async def listar_precios(
    id: int,
    params: ParamsPaginacion = Depends(),
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> PaginatedResponse[HistorialPrecioResponse]:
    """Historial de sólo lectura, del cambio más reciente al más antiguo."""
    return await CatalogoService.listar_precios(id, params.page, params.size, uow)
