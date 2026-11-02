"""Servicios del ciclo de vida de las órdenes de trabajo.

Reglas de negocio aplicadas:
- RN-10: la orden nace `PENDIENTE`, con al menos un ítem, sin repuestos
  repetidos, precios copiados del repuesto y total calculado en el servidor.
- RN-11: transiciones válidas `PENDIENTE -> EN_REPARACION -> TERMINADA` y
  `PENDIENTE -> CANCELADA`.
- RN-12: la cancelación evalúa permisos antes que el estado.
- RN-13: la terminación descuenta stock e inserta movimientos e historial en un
  único Unit of Work atómico; si falta stock, revierte todo.
- RN-17: `/mis-ordenes` filtra por el cliente del usuario autenticado.
- RN-19: el catálogo de estados sólo se lee.
"""

import asyncio
import logging
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
from app.modules.repuestos.models import MovimientoStock

logger = logging.getLogger(__name__)

ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_EN_REPARACION = "EN_REPARACION"
ESTADO_TERMINADA = "TERMINADA"
ESTADO_CANCELADA = "CANCELADA"

ROLES_PERSONAL = frozenset({"ADMIN", "RECEPCION", "MECANICO"})
ROLES_TERMINAR = frozenset({"ADMIN"})
ROLES_CANCELAR = frozenset({"ADMIN", "RECEPCION"})


def _es_personal(actor: UsuarioActual) -> bool:
    return bool(ROLES_PERSONAL.intersection(actor.roles))


def _cliente_es_duenio(orden: OrdenTrabajo, actor: UsuarioActual) -> bool:
    vehiculo = orden.vehiculo
    if vehiculo is None or vehiculo.cliente is None:
        return False
    return vehiculo.cliente.usuario_id == actor.id


def _no_encontrada() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Orden de trabajo no encontrada",
    )


def _subtotal(item: ItemOrden) -> Decimal:
    return item.precio_unitario * item.cantidad


def armar_item_response(item: ItemOrden) -> ItemOrdenResponse:
    return _item_response(item, item.repuesto)


def _item_response(item: ItemOrden, repuesto) -> ItemOrdenResponse:
    """Ítem con su repuesto ya resuelto (evita carga perezosa en async)."""
    return ItemOrdenResponse(
        repuesto_id=item.repuesto_id,
        codigo=repuesto.codigo,
        descripcion=repuesto.descripcion,
        cantidad=item.cantidad,
        precio_unitario=item.precio_unitario,
        subtotal=_subtotal(item),
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


def _historial_ordenado(
    historial: list[HistorialEstadoOrden],
) -> list[HistorialEstadoOrden]:
    return sorted(
        historial,
        key=lambda registro: (registro.cuando, registro.id or 0),
    )


def armar_orden_response(
    orden: OrdenTrabajo,
    historial_extra: HistorialEstadoOrden | None = None,
) -> OrdenResponse:
    """Construye el detalle usando relaciones ya precargadas (sin N+1)."""
    historial = list(orden.historial_estados)
    if historial_extra is not None:
        historial.append(historial_extra)

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
            armar_historial_response(registro)
            for registro in _historial_ordenado(historial)
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


async def avisar_cliente_simulado(orden_id: int, destinatario: str) -> None:
    """Aviso simulado (Ej. 8): corre después del commit y nunca rompe la respuesta."""
    try:
        await asyncio.sleep(0.5)
        logger.info(
            "Aviso simulado: orden %s terminada. Se notificó a %s",
            orden_id,
            destinatario,
        )
    except Exception:  # pragma: no cover - defensivo, no debe tumbar el request
        logger.exception("Falló el aviso simulado de la orden %s", orden_id)


class OrdenService:
    """Casos de uso del ciclo de vida de las órdenes de trabajo."""

    @staticmethod
    async def listar_estados(
        uow: OrdenesUnitOfWork,
    ) -> list[EstadoOrdenResponse]:
        """Catálogo de estados, ordenado por posición (sólo lectura)."""
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
        """Crea la orden `PENDIENTE` con precios copiados y total calculado (RN-10)."""
        async with uow:
            pendiente = await uow.estados.get_by_codigo(ESTADO_PENDIENTE)
            if pendiente is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "El catálogo de estados está vacío o no contiene "
                        "'PENDIENTE': no se puede crear la orden"
                    ),
                )

            vehiculo = await uow.vehiculos.get_by_id_con_cliente(dto.vehiculo_id)
            if vehiculo is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El vehículo indicado no existe o está dado de baja",
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

            orden = await uow.ordenes.add(
                OrdenTrabajo(
                    vehiculo_id=vehiculo.id,
                    mecanico_id=None,
                    estado=ESTADO_PENDIENTE,
                    falla=dto.falla,
                    total=total,
                )
            )

            items: list[ItemOrden] = []
            items_response: list[ItemOrdenResponse] = []
            for item_dto in dto.items:
                repuesto = repuestos[item_dto.repuesto_id]
                item = await uow.items.add(
                    ItemOrden(
                        orden_id=orden.id,
                        repuesto_id=repuesto.id,
                        cantidad=item_dto.cantidad,
                        precio_unitario=repuesto.precio,
                    )
                )
                items.append(item)
                items_response.append(_item_response(item, repuesto))

            historial = await uow.historial.add(
                HistorialEstadoOrden(
                    orden_id=orden.id,
                    desde_estado=None,
                    hasta_estado=ESTADO_PENDIENTE,
                    usuario_id=actor.id,
                )
            )

            # Se arma la respuesta con los objetos ya cargados, antes de refrescar.
            return OrdenResponse(
                id=orden.id,
                estado=orden.estado,
                patente=vehiculo.patente,
                creada_en=orden.creada_en,
                total=orden.total,
                mecanico_id=None,
                falla=orden.falla,
                cliente=vehiculo.cliente.nombre,
                items=items_response,
                historial=[armar_historial_response(historial)],
            )

    @staticmethod
    async def listar_ordenes(
        estado: str | None,
        page: int,
        size: int,
        uow: OrdenesUnitOfWork,
    ) -> PaginatedResponse[OrdenResumenResponse]:
        """Listado paginado con filtro exacto por estado."""
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
        """Órdenes de los vehículos del cliente autenticado (RN-17)."""
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
        """Detalle con carga anticipada; el cliente sólo ve sus órdenes."""
        async with uow:
            orden = await uow.ordenes.get_detalle(orden_id)
            if orden is None:
                raise _no_encontrada()

            if not _es_personal(actor) and not _cliente_es_duenio(orden, actor):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tiene permiso para consultar esta orden",
                )

            return armar_orden_response(orden)

    @staticmethod
    async def iniciar_orden(
        orden_id: int,
        actor: UsuarioActual,
        uow: OrdenesUnitOfWork,
    ) -> OrdenResponse:
        """Autoasigna el mecánico y pasa la orden a `EN_REPARACION` (RN-11)."""
        async with uow:
            orden = await uow.ordenes.get_para_actualizar(orden_id)
            if orden is None:
                raise _no_encontrada()

            if orden.estado != ESTADO_PENDIENTE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Sólo una orden PENDIENTE puede iniciarse",
                )

            orden.mecanico_id = actor.id
            orden.estado = ESTADO_EN_REPARACION

            historial = await uow.historial.add(
                HistorialEstadoOrden(
                    orden_id=orden.id,
                    desde_estado=ESTADO_PENDIENTE,
                    hasta_estado=ESTADO_EN_REPARACION,
                    usuario_id=actor.id,
                )
            )
            response = armar_orden_response(orden, historial_extra=historial)
            await uow.ordenes.update(orden)
            return response

    @staticmethod
    async def terminar_orden(
        orden_id: int,
        actor: UsuarioActual,
        uow: OrdenesUnitOfWork,
    ) -> OrdenResponse:
        """Termina la orden descontando stock en un único UoW atómico (RN-13)."""
        async with uow:
            orden = await uow.ordenes.get_para_actualizar(orden_id)
            if orden is None:
                raise _no_encontrada()

            es_mecanico_asignado = actor.id == orden.mecanico_id
            if not es_mecanico_asignado and not ROLES_TERMINAR.intersection(actor.roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Sólo el mecánico asignado o un administrador puede "
                        "terminar la orden"
                    ),
                )

            if orden.estado != ESTADO_EN_REPARACION:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La orden no está en estado EN_REPARACION",
                )

            # Bloqueo determinista por repuesto_id ascendente: evita interbloqueos.
            items_ordenados = sorted(orden.items, key=lambda item: item.repuesto_id)
            repuestos = []
            for item in items_ordenados:
                repuesto = await uow.repuestos.get_para_actualizar(item.repuesto_id)
                if repuesto is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Uno de los repuestos de la orden ya no está vigente: "
                            "no se puede terminar"
                        ),
                    )
                repuestos.append((item, repuesto))

            faltantes = [
                repuesto.codigo
                for item, repuesto in repuestos
                if repuesto.stock < item.cantidad
            ]
            if faltantes:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Stock insuficiente para: " + ", ".join(sorted(faltantes))
                    ),
                )

            for item, repuesto in repuestos:
                repuesto.stock -= item.cantidad
                await uow.movimientos.add(
                    MovimientoStock(
                        repuesto_id=repuesto.id,
                        orden_id=orden.id,
                        usuario_id=actor.id,
                        cantidad=-item.cantidad,
                        motivo=f"Salida por orden {orden.id}",
                    )
                )

            orden.estado = ESTADO_TERMINADA

            historial = await uow.historial.add(
                HistorialEstadoOrden(
                    orden_id=orden.id,
                    desde_estado=ESTADO_EN_REPARACION,
                    hasta_estado=ESTADO_TERMINADA,
                    usuario_id=actor.id,
                )
            )
            response = armar_orden_response(orden, historial_extra=historial)
            await uow.ordenes.update(orden)
            return response

    @staticmethod
    async def cancelar_orden(
        orden_id: int,
        actor: UsuarioActual,
        uow: OrdenesUnitOfWork,
    ) -> OrdenResponse:
        """Cancela evaluando permisos antes que estado (RN-12)."""
        async with uow:
            orden = await uow.ordenes.get_para_actualizar(orden_id)
            if orden is None:
                raise _no_encontrada()

            autorizado = _cliente_es_duenio(orden, actor) or bool(
                ROLES_CANCELAR.intersection(actor.roles)
            )
            if not autorizado:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tiene permiso para cancelar esta orden",
                )

            if orden.estado != ESTADO_PENDIENTE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Sólo una orden PENDIENTE puede cancelarse",
                )

            orden.estado = ESTADO_CANCELADA

            historial = await uow.historial.add(
                HistorialEstadoOrden(
                    orden_id=orden.id,
                    desde_estado=ESTADO_PENDIENTE,
                    hasta_estado=ESTADO_CANCELADA,
                    usuario_id=actor.id,
                )
            )
            response = armar_orden_response(orden, historial_extra=historial)
            await uow.ordenes.update(orden)
            return response
