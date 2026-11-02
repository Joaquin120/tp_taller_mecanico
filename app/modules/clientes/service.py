from fastapi import HTTPException, status

from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.clientes.schemas import ClienteCreateRequest, VehiculoCreateRequest
from app.modules.clientes.unit_of_work import ClientesUnitOfWork


class ClienteService:
    """Lógica de negocio para la gestión de clientes."""

    @staticmethod
    async def crear_cliente(
        payload: ClienteCreateRequest,
        uow: ClientesUnitOfWork,
    ) -> Cliente:
        """Crea un nuevo cliente verificando unicidad de documento (RN-01)."""
        async with uow:
            existente = await uow.clientes.get_by_documento(payload.documento)
            if existente is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ya existe un cliente registrado con ese documento",
                )

            cliente = Cliente(
                nombre=payload.nombre,
                documento=payload.documento,
                telefono=payload.telefono,
            )
            return await uow.clientes.add(cliente)

    @staticmethod
    async def obtener_cliente(
        cliente_id: int,
        uow: ClientesUnitOfWork,
    ) -> Cliente:
        """Obtiene un cliente por ID precargando sus vehículos vigentes."""
        async with uow:
            cliente = await uow.clientes.get_by_id_con_vehiculos(cliente_id)
            if cliente is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cliente no encontrado",
                )
            return cliente


class VehiculoService:
    """Lógica de negocio para la gestión de flota de vehículos."""

    @staticmethod
    async def crear_vehiculo(
        cliente_id: int,
        payload: VehiculoCreateRequest,
        uow: ClientesUnitOfWork,
    ) -> Vehiculo:
        """Registra un vehículo para un cliente validando patente única vigente (RN-01)."""
        async with uow:
            cliente = await uow.clientes.get_by_id(cliente_id)
            if cliente is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cliente no encontrado",
                )

            existente = await uow.vehiculos.get_by_patente(payload.patente)
            if existente is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ya existe un vehículo vigente registrado con esa patente",
                )

            vehiculo = Vehiculo(
                cliente_id=cliente_id,
                patente=payload.patente,
                marca=payload.marca,
                modelo=payload.modelo,
                anio=payload.anio,
            )
            return await uow.vehiculos.add(vehiculo)

    @staticmethod
    async def baja_vehiculo(
        vehiculo_id: int,
        uow: ClientesUnitOfWork,
    ) -> None:
        """Realiza la baja lógica de un vehículo verificando órdenes abiertas (RN-16)."""
        async with uow:
            vehiculo = await uow.vehiculos.get_by_id(vehiculo_id)
            if vehiculo is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Vehículo no encontrado o ya dado de baja",
                )

            ordenes_abiertas = await uow.ordenes.contar_ordenes_abiertas(vehiculo_id)
            if ordenes_abiertas > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No se puede dar de baja un vehículo con órdenes de trabajo abiertas",
                )

            await uow.vehiculos.soft_delete(vehiculo)

    @staticmethod
    async def listar_mis_vehiculos(
        usuario_id: int,
        uow: ClientesUnitOfWork,
    ) -> list[Vehiculo]:
        """Obtiene la lista de vehículos vigentes del cliente autenticado (RN-17)."""
        async with uow:
            cliente = await uow.clientes.get_by_usuario_id(usuario_id)
            if cliente is None:
                return []
            vehiculos = await uow.vehiculos.listar_por_cliente(cliente.id)
            return list(vehiculos)
