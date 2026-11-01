from decimal import Decimal

from fastapi import HTTPException, status

from app.core.auth import UsuarioActual
from app.core.paginacion import PaginatedResponse, armar_paginacion
from app.modules.ordenes.models import (
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.ordenes.schemas import (
    EstadoOrdenResponse,
    HistorialEstadoResponse,
    ItemOrdenResponse,
    OrdenCrearRequest,
    OrdenResponse,
    OrdenResumenResponse,
)
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.repuestos.repository import StockInsuficienteError

ROLES_PERSONAL = {"ADMIN", "RECEPCION", "MECANICO"}


def _es_personal(actor: UsuarioActual) -> bool:
    return any(rol in ROLES_PERSONAL for rol in actor.roles)


def armar_item_response(item: ItemOrden) -> ItemOrdenResponse:
    precio = item.precio_unitario
    return ItemOrdenResponse(
        repuesto_id=item.repuesto_id,
        codigo=item.repuesto.codigo,
        descripcion=item.repuesto.descripcion,
        cantidad=item.cantidad,
        precio_unitario=precio,
        subtotal=precio * item.cantidad,
    )


def armar_historial_response(
    historial: HistorialEstadoOrden,
) -> HistorialEstadoResponse:
    return HistorialEstadoResponse(
        desde_estado=historial.desde_estado,
        hasta_estado=historial.hasta_estado,
        usuario_id=historial.usuario_id,
        cuando=historial.cuando,
    )


def armar_orden_response(orden: OrdenTrabajo) -> OrdenResponse:
    return OrdenResponse(
        id=orden.id,
        estado=orden.estado,
        patente=orden.vehiculo.patente,
        creada_en=orden.creada_en,
        total=orden.total,
        mecanico_id=orden.mecanico_id,
        falla=orden.falla,
        cliente=orden.vehiculo.cliente.nombre,
        items=[armar_item_response(item) for item in orden.items],
        historial=[
            armar_historial_response(historial)
            for historial in orden.historial_estados
        ],
    )


def armar_resumen_response(orden: OrdenTrabajo) -> OrdenResumenResponse:
    return OrdenResumenResponse(
        id=orden.id,
        estado=orden.estado,
        vehiculo_id=orden.vehiculo_id,
        patente=orden.vehiculo.patente,
        mecanico_id=orden.mecanico_id,
        falla=orden.falla,
        creada_en=orden.creada_en,
        total=orden.total,
    )


class OrdenService:
    """Reglas de negocio del ciclo de vida de las órdenes de trabajo."""

    @staticmethod
    async def listar_estados(
        uow: OrdenesUnitOfWork,
    ) -> list[EstadoOrdenResponse]:
        async with uow:
            estados = await uow.estados.listar_por_posicion()
            return [
                EstadoOrdenResponse(
                    codigo=estado.codigo,
                    descripcion=estado.descripcion,
                    posicion=estado.posicion,
                    es_final=estado.es_final,
                )
                for estado in estados
            ]

    @staticmethod
    async def crear_orden(
        dto: OrdenCrearRequest,
        actor: UsuarioActual,
        uow: OrdenesUnitOfWork,
    ) -> OrdenResponse:
        """Crea una orden PENDIENTE en un único Unit of Work (RN-10)."""
        async with uow:
            if await uow.estados.contar() == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El catálogo de estados está vacío: no se puede crear la orden",
                )

            vehiculo = await uow.vehiculos.get_by_id_con_cliente(dto.vehiculo_id)
            if vehiculo is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El vehículo indicado no existe o está dado de baja",
                )

            ids_repuestos = [item.repuesto_id for item in dto.items]
            if len(ids_repuestos) != len(set(ids_repuestos)):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="No se puede repetir un repuesto en la misma orden",
                )

            repuestos = {}
            total = Decimal("0.00")
            for item_dto in dto.items:
                repuesto = await uow.repuestos.get_by_id(item_dto.repuesto_id)
                if repuesto is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="El repuesto indicado no existe o está dado de baja",
                    )
                repuestos[item_dto.repuesto_id] = repuesto
                total += repuesto.precio * item_dto.cantidad

            orden = OrdenTrabajo(
                vehiculo_id=vehiculo.id,
                mecanico_id=None,
                estado="PENDIENTE",
                falla=dto.falla,
                total=total,
            )
            orden = await uow.ordenes.add(orden)

            items: list[ItemOrden] = []
            for item_dto in dto.items:
                repuesto = repuestos[item_dto.repuesto_id]
                item = ItemOrden(
                    orden_id=orden.id,
                    repuesto_id=repuesto.id,
                    cantidad=item_dto.cantidad,
                    precio_unitario=repuesto.precio,
                )
                item = await uow.items.add(item)
                item.repuesto = repuesto
                items.append(item)

            historial = HistorialEstadoOrden(
                orden_id=orden.id,
                desde_estado=None,
                hasta_estado="PENDIENTE",
                usuario_id=actor.id,
            )
            await uow.historial.add(historial)

            orden.vehiculo = vehiculo
            orden.items = items
            orden.historial_estados = [historial]
            return armar_orden_response(orden)

    @staticmethod
    async def listar_ordenes(
        estado: str | None,
        page: int,
        size: int,
        uow: OrdenesUnitOfWork,
    ) -> PaginatedResponse[OrdenResumenResponse]:
        async with uow:
            total = await uow.ordenes.contar_por_estado(estado)
            ordenes = await uow.ordenes.listar(
                estado,
                offset=(page - 1) * size,
                limit=size,
            )
            items = [armar_resumen_response(orden) for orden in ordenes]

        return armar_paginacion(items, total, page, size)

    @staticmethod
    async def listar_mis_ordenes(
        actor: UsuarioActual,
        page: int,
        size: int,
        uow: OrdenesUnitOfWork,
    ) -> PaginatedResponse[OrdenResumenResponse]:
        async with uow:
            total = await uow.ordenes.contar_por_cliente_usuario(actor.id)
            ordenes = await uow.ordenes.listar_por_cliente_usuario(
                actor.id,
                offset=(page - 1) * size,
                limit=size,
            )
            items = [armar_resumen_response(orden) for orden in ordenes]

        return armar_paginacion(items, total, page, size)

    @staticmethod
    async def obtener_orden(
        orden_id: int,
        actor: UsuarioActual,
        uow: OrdenesUnitOfWork,
    ) -> OrdenResponse:
        async with uow:
            orden = await uow.ordenes.get_detalle(orden_id)
            if orden is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Orden no encontrada",
                )

            es_duenio = (
                orden.vehiculo is not None
                and orden.vehiculo.cliente is not None
                and orden.vehiculo.cliente.usuario_id == actor.id
            )
            if not _es_personal(actor) and not es_duenio:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tiene permiso para consultar esta orden",
                )

            return armar_orden_response(orden)

    @staticmethod
    async def terminar_orden(
        orden_id: int,
        actor: UsuarioActual,
        uow: OrdenesUnitOfWork,
    ) -> OrdenResponse:
        """Termina la orden descontando stock en un único Unit of Work (RN-13)."""
        async with uow:
            orden = await uow.ordenes.get_detalle(orden_id)
            if orden is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Orden no encontrada",
                )

            if actor.id != orden.mecanico_id and "ADMIN" not in actor.roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sólo el mecánico asignado o un administrador puede terminar la orden",
                )

            if orden.estado != "EN_REPARACION":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La orden no está en estado EN_REPARACION",
                )

            for item in orden.items:
                if item.repuesto.stock < item.cantidad:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Stock insuficiente para el repuesto {item.repuesto.codigo}"
                        ),
                    )

            try:
                for item in orden.items:
                    await uow.movimientos.registrar_movimiento(
                        repuesto=item.repuesto,
                        cantidad=-item.cantidad,
                        motivo=f"Salida por orden {orden.id}",
                        usuario_id=actor.id,
                        orden_id=orden.id,
                    )
            except StockInsuficienteError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc

            estado_anterior = orden.estado
            orden.estado = "TERMINADA"

            historial = HistorialEstadoOrden(
                orden_id=orden.id,
                desde_estado=estado_anterior,
                hasta_estado="TERMINADA",
                usuario_id=actor.id,
            )
            await uow.historial.add(historial)
            orden.historial_estados.append(historial)

            response = armar_orden_response(orden)
            await uow.ordenes.update(orden)
            return response
