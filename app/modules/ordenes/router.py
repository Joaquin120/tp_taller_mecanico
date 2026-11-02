"""Router del ciclo de vida de las órdenes de trabajo.

RBAC (matriz de la KB):
- `GET /estados-orden`: cualquier usuario autenticado (sólo lectura).
- `POST /ordenes`: ADMIN y RECEPCION.
- `GET /ordenes`: ADMIN, RECEPCION y MECANICO.
- `GET /ordenes/{id}`: personal o cliente dueño del vehículo.
- `POST /ordenes/{id}/iniciar`: sólo MECANICO.
- `POST /ordenes/{id}/terminar`: mecánico asignado o ADMIN.
- `POST /ordenes/{id}/cancelar`: ADMIN, RECEPCION o cliente dueño.
- `GET /mis-ordenes`: cualquier autenticado, filtrado por su cliente.
"""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
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
from app.modules.ordenes.service import OrdenService, avisar_cliente_simulado
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork

EstadoOrdenLiteral = Literal["PENDIENTE", "EN_REPARACION", "TERMINADA", "CANCELADA"]

router_protegido = APIRouter(prefix="", tags=["ordenes"])


async def get_ordenes_uow(
    session: AsyncSession = Depends(get_session),
) -> OrdenesUnitOfWork:
    """Construye el Unit of Work con la sesión de la dependencia."""
    return OrdenesUnitOfWork(session)


@router_protegido.get(
    "/estados-orden",
    response_model=list[EstadoOrdenResponse],
    status_code=status.HTTP_200_OK,
    summary="Catálogo de estados de orden por posición",
)
async def listar_estados(
    actor: UsuarioActual = Depends(get_current_user),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> list[EstadoOrdenResponse]:
    """Devuelve el catálogo de sólo lectura ordenado por `posicion`."""
    return await OrdenService.listar_estados(uow)


@router_protegido.post(
    "/ordenes",
    response_model=OrdenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de orden de trabajo en estado PENDIENTE",
)
async def crear_orden(
    payload: OrdenCrearRequest,
    actor: UsuarioActual = Depends(requiere_rol("RECEPCION", "ADMIN")),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenResponse:
    """Crea la orden con precios copiados y total calculado en el servidor."""
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
    """Lista órdenes filtradas por estado exacto, de la más reciente a la más antigua."""
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
    """Filtra por el cliente vinculado al usuario autenticado (RN-17)."""
    return await OrdenService.listar_mis_ordenes(actor, params.page, params.size, uow)


@router_protegido.get(
    "/ordenes/{orden_id}",
    response_model=OrdenResponse,
    status_code=status.HTTP_200_OK,
    summary="Detalle de una orden con carga anticipada",
)
async def obtener_orden(
    orden_id: int,
    actor: UsuarioActual = Depends(get_current_user),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenResponse:
    """Devuelve el detalle sin N+1; el cliente sólo accede a sus órdenes."""
    return await OrdenService.obtener_orden(orden_id, actor, uow)


@router_protegido.post(
    "/ordenes/{orden_id}/iniciar",
    response_model=OrdenResponse,
    status_code=status.HTTP_200_OK,
    summary="Inicio de una orden por el mecánico",
)
async def iniciar_orden(
    orden_id: int,
    actor: UsuarioActual = Depends(requiere_rol("MECANICO")),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenResponse:
    """Autoasigna el mecánico y pasa la orden a EN_REPARACION."""
    return await OrdenService.iniciar_orden(orden_id, actor, uow)


@router_protegido.post(
    "/ordenes/{orden_id}/terminar",
    response_model=OrdenResponse,
    status_code=status.HTTP_200_OK,
    summary="Terminar una orden descontando stock",
)
async def terminar_orden(
    orden_id: int,
    background_tasks: BackgroundTasks,
    actor: UsuarioActual = Depends(get_current_user),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenResponse:
    """Descuenta stock y registra movimientos/historial en un único UoW (RN-13).

    El aviso simulado se agenda **después** de que el servicio retorna, es decir,
    con el commit ya confirmado: si la terminación falla, la tarea no se agenda.
    """
    response = await OrdenService.terminar_orden(orden_id, actor, uow)
    background_tasks.add_task(avisar_cliente_simulado, response.id, response.cliente)
    return response


@router_protegido.post(
    "/ordenes/{orden_id}/cancelar",
    response_model=OrdenResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancelación de una orden PENDIENTE",
)
async def cancelar_orden(
    orden_id: int,
    actor: UsuarioActual = Depends(get_current_user),
    uow: OrdenesUnitOfWork = Depends(get_ordenes_uow),
) -> OrdenResponse:
    """Evalúa permisos antes que estado: 403 antes que 409 (RN-12)."""
    return await OrdenService.cancelar_orden(orden_id, actor, uow)
