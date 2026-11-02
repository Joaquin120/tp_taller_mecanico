from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UsuarioActual, requiere_rol
from app.core.database import get_session
from app.modules.clientes.schemas import (
    ClienteCreateRequest,
    ClienteDetalleResponse,
    ClienteResponse,
    VehiculoCreateRequest,
    VehiculoResponse,
)
from app.modules.clientes.service import ClienteService, VehiculoService
from app.modules.clientes.unit_of_work import ClientesUnitOfWork

router_protegido = APIRouter(tags=["clientes"])


async def get_clientes_uow(
    session: AsyncSession = Depends(get_session),
) -> ClientesUnitOfWork:
    """El router construye el Unit of Work con la sesión de la dependencia."""
    return ClientesUnitOfWork(session)


@router_protegido.post(
    "/clientes",
    response_model=ClienteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de cliente",
)
async def crear_cliente(
    payload: ClienteCreateRequest,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN", "RECEPCION")),
    uow: ClientesUnitOfWork = Depends(get_clientes_uow),
) -> ClienteResponse:
    """Registra un nuevo cliente validando documento único (RN-01)."""
    return await ClienteService.crear_cliente(payload, uow)


@router_protegido.get(
    "/clientes/{cliente_id}",
    response_model=ClienteDetalleResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta de cliente por ID con sus vehículos vigentes",
)
async def obtener_cliente(
    cliente_id: int,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN", "RECEPCION")),
    uow: ClientesUnitOfWork = Depends(get_clientes_uow),
) -> ClienteDetalleResponse:
    """Obtiene un cliente por ID precargando sus vehículos no borrados."""
    return await ClienteService.obtener_cliente(cliente_id, uow)


@router_protegido.post(
    "/clientes/{cliente_id}/vehiculos",
    response_model=VehiculoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registro de vehículo para un cliente",
)
async def crear_vehiculo(
    cliente_id: int,
    payload: VehiculoCreateRequest,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN", "RECEPCION")),
    uow: ClientesUnitOfWork = Depends(get_clientes_uow),
) -> VehiculoResponse:
    """Registra un vehículo para un cliente validando patente única vigente (RN-01)."""
    return await VehiculoService.crear_vehiculo(cliente_id, payload, uow)


@router_protegido.delete(
    "/vehiculos/{vehiculo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Baja lógica de vehículo",
)
async def baja_vehiculo(
    vehiculo_id: int,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN", "RECEPCION")),
    uow: ClientesUnitOfWork = Depends(get_clientes_uow),
) -> None:
    """Baja lógica de vehículo, rechazada con 409 si tiene órdenes abiertas (RN-16)."""
    await VehiculoService.baja_vehiculo(vehiculo_id, uow)


@router_protegido.get(
    "/mis-vehiculos",
    response_model=list[VehiculoResponse],
    status_code=status.HTTP_200_OK,
    summary="Consulta de vehículos propios del cliente autenticado",
)
async def listar_mis_vehiculos(
    actor: UsuarioActual = Depends(requiere_rol("CLIENTE")),
    uow: ClientesUnitOfWork = Depends(get_clientes_uow),
) -> list[VehiculoResponse]:
    """Retorna exclusivamente los vehículos vigentes del cliente autenticado (RN-17)."""
    return await VehiculoService.listar_mis_vehiculos(actor.id, uow)
