from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UsuarioActual, get_current_user, requiere_rol
from app.core.database import get_session
from app.core.paginacion import PaginatedResponse, ParamsPaginacion
from app.modules.ordenes.schemas import (
    EstadoOrdenResponse,
    OrdenCrearRequest,
    OrdenResponse,
    OrdenResumenResponse,
)
from app.modules.ordenes.service import OrdenService
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork

EstadoOrdenLiteral = Literal["PENDIENTE", "EN_REPARACION", "TERMINADA", "CANCELADA"]

router_protegido = APIRouter(prefix="", tags=["ordenes"])


async def get_ordenes_uow(
    session: AsyncSession = Depends(get_session),
) -> OrdenesUnitOfWork:
    """El router construye el Unit of Work con la sesión de la dependencia."""
    return OrdenesUnitOfWork(session)


@router_protegido.get(
    "/estados-orden",
    response_model=list[EstadoOrdenResponse],
    status_code=status.HTTP_200_OK,
    summary="Catálogo de estados de orden por posición",
)
async def listar_estados(
    usuario: UsuarioActual = Depends(get_current_user),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> list[EstadoOrdenResponse]:
    return await OrdenService.listar_estados(uow)


@router_protegido.post(
    "/ordenes",
    response_model=OrdenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de orden de trabajo",
)
async def crear_orden(
    payload: OrdenCrearRequest,
    actor: UsuarioActual = Depends(requiere_rol("RECEPCION", "ADMIN")),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenResponse:
    return await OrdenService.crear_orden(payload, actor, uow)


@router_protegido.get(
    "/ordenes",
    response_model=PaginatedResponse[OrdenResumenResponse],
    status_code=status.HTTP_200_OK,
    summary="Listado paginado de órdenes",
)
async def listar_ordenes(
    params: ParamsPaginacion = Depends(),
    estado: EstadoOrdenLiteral | None = Query(default=None),
    actor: UsuarioActual = Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO")),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> PaginatedResponse[OrdenResumenResponse]:
    return await OrdenService.listar_ordenes(estado, params.page, params.size, uow)


@router_protegido.get(
    "/mis-ordenes",
    response_model=PaginatedResponse[OrdenResumenResponse],
    status_code=status.HTTP_200_OK,
    summary="Órdenes de los vehículos del cliente autenticado",
)
async def listar_mis_ordenes(
    params: ParamsPaginacion = Depends(),
    actor: UsuarioActual = Depends(get_current_user),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> PaginatedResponse[OrdenResumenResponse]:
    return await OrdenService.listar_mis_ordenes(actor, params.page, params.size, uow)


@router_protegido.get(
    "/ordenes/{orden_id}",
    response_model=OrdenResponse,
    status_code=status.HTTP_200_OK,
    summary="Detalle de una orden",
)
async def obtener_orden(
    orden_id: int,
    actor: UsuarioActual = Depends(get_current_user),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenResponse:
    return await OrdenService.obtener_orden(orden_id, actor, uow)


@router_protegido.post(
    "/ordenes/{orden_id}/terminar",
    response_model=OrdenResponse,
    status_code=status.HTTP_200_OK,
    summary="Terminar una orden descontando stock",
)
async def terminar_orden(
    orden_id: int,
    actor: UsuarioActual = Depends(get_current_user),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenResponse:
    return await OrdenService.terminar_orden(orden_id, actor, uow)
