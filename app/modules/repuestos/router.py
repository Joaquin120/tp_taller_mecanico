from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UsuarioActual, requiere_rol
from app.core.database import get_session
from app.core.paginacion import PaginatedResponse, ParamsPaginacion
from app.modules.repuestos.schemas import (
    HistorialPrecioResponse,
    MovimientoStockResponse,
    ReponerStockRequest,
    RepuestoActualizarRequest,
    RepuestoCrearRequest,
    RepuestoResponse,
)
from app.modules.repuestos.service import RepuestoService
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork

router_protegido = APIRouter(prefix="/repuestos", tags=["repuestos"])


async def get_repuestos_uow(
    session: AsyncSession = Depends(get_session),
) -> RepuestosUnitOfWork:
    """El router construye el Unit of Work con la sesión de la dependencia."""
    return RepuestosUnitOfWork(session)


@router_protegido.get(
    "",
    response_model=PaginatedResponse[RepuestoResponse],
    status_code=status.HTTP_200_OK,
    summary="Listado paginado de repuestos",
)
async def listar_repuestos(
    params: ParamsPaginacion = Depends(),
    q: str | None = Query(default=None, max_length=255),
    actor: UsuarioActual = Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> PaginatedResponse[RepuestoResponse]:
    return await RepuestoService.listar(q, params.page, params.size, uow)


@router_protegido.get(
    "/{repuesto_id}",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
    summary="Detalle de un repuesto",
)
async def obtener_repuesto(
    repuesto_id: int,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> RepuestoResponse:
    return await RepuestoService.obtener(repuesto_id, uow)


@router_protegido.post(
    "",
    response_model=RepuestoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de repuesto con stock inicial",
)
async def crear_repuesto(
    payload: RepuestoCrearRequest,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> RepuestoResponse:
    return await RepuestoService.crear(payload, actor, uow)


@router_protegido.patch(
    "/{repuesto_id}",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
    summary="Modificación de descripción y precio",
)
async def actualizar_repuesto(
    repuesto_id: int,
    payload: RepuestoActualizarRequest,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> RepuestoResponse:
    return await RepuestoService.actualizar(repuesto_id, payload, actor, uow)


@router_protegido.delete(
    "/{repuesto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Baja lógica de un repuesto",
)
async def eliminar_repuesto(
    repuesto_id: int,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> None:
    await RepuestoService.eliminar(repuesto_id, uow)


@router_protegido.post(
    "/{repuesto_id}/reponer",
    response_model=RepuestoResponse,
    status_code=status.HTTP_200_OK,
    summary="Reposición de stock",
)
async def reponer_stock(
    repuesto_id: int,
    payload: ReponerStockRequest,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> RepuestoResponse:
    return await RepuestoService.reponer(repuesto_id, payload, actor, uow)


@router_protegido.get(
    "/{repuesto_id}/movimientos",
    response_model=list[MovimientoStockResponse],
    status_code=status.HTTP_200_OK,
    summary="Movimientos de stock de un repuesto",
)
async def listar_movimientos(
    repuesto_id: int,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> list[MovimientoStockResponse]:
    return await RepuestoService.listar_movimientos(repuesto_id, uow)


@router_protegido.get(
    "/{repuesto_id}/precios",
    response_model=list[HistorialPrecioResponse],
    status_code=status.HTTP_200_OK,
    summary="Historial de precios de un repuesto",
)
async def listar_precios(
    repuesto_id: int,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: RepuestosUnitOfWork = Depends(get_repuestos_uow),
) -> list[HistorialPrecioResponse]:
    return await RepuestoService.listar_precios(repuesto_id, uow)
