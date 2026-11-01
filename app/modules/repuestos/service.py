from decimal import Decimal

from fastapi import HTTPException, status

from app.core.auth import UsuarioActual
from app.core.paginacion import PaginatedResponse, armar_paginacion
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.repuestos.repository import StockInsuficienteError
from app.modules.repuestos.schemas import (
    HistorialPrecioResponse,
    MovimientoStockResponse,
    ReponerStockRequest,
    RepuestoActualizarRequest,
    RepuestoCrearRequest,
    RepuestoResponse,
)
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork


def armar_repuesto_response(repuesto: Repuesto) -> RepuestoResponse:
    return RepuestoResponse(
        id=repuesto.id,
        codigo=repuesto.codigo,
        descripcion=repuesto.descripcion,
        precio=repuesto.precio,
        stock=repuesto.stock,
    )


def armar_movimiento_response(movimiento: MovimientoStock) -> MovimientoStockResponse:
    return MovimientoStockResponse(
        id=movimiento.id,
        repuesto_id=movimiento.repuesto_id,
        orden_id=movimiento.orden_id,
        usuario_id=movimiento.usuario_id,
        cantidad=movimiento.cantidad,
        motivo=movimiento.motivo,
        cuando=movimiento.cuando,
    )


def armar_historial_response(
    historial: HistorialPrecioRepuesto,
) -> HistorialPrecioResponse:
    return HistorialPrecioResponse(
        id=historial.id,
        repuesto_id=historial.repuesto_id,
        usuario_id=historial.usuario_id,
        precio_anterior=historial.precio_anterior,
        precio_nuevo=historial.precio_nuevo,
        cuando=historial.cuando,
    )


class RepuestoService:
    """Reglas de negocio del catálogo de repuestos y del stock."""

    @staticmethod
    async def listar(
        q: str | None,
        page: int,
        size: int,
        uow: RepuestosUnitOfWork,
    ) -> PaginatedResponse[RepuestoResponse]:
        async with uow:
            total = await uow.repuestos.contar_por_descripcion(q)
            repuestos = await uow.repuestos.buscar_por_descripcion(
                q,
                offset=(page - 1) * size,
                limit=size,
            )
            items = [armar_repuesto_response(repuesto) for repuesto in repuestos]

        return armar_paginacion(items, total, page, size)

    @staticmethod
    async def obtener(
        repuesto_id: int,
        uow: RepuestosUnitOfWork,
    ) -> RepuestoResponse:
        async with uow:
            repuesto = await uow.repuestos.get_by_id(repuesto_id)
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado",
                )
            return armar_repuesto_response(repuesto)

    @staticmethod
    async def crear(
        dto: RepuestoCrearRequest,
        actor: UsuarioActual,
        uow: RepuestosUnitOfWork,
    ) -> RepuestoResponse:
        async with uow:
            repuesto = Repuesto(
                codigo=dto.codigo,
                descripcion=dto.descripcion,
                precio=dto.precio,
                stock=0,
            )
            repuesto = await uow.repuestos.add(repuesto)

            if dto.stock_inicial > 0:
                await uow.movimientos.registrar_movimiento(
                    repuesto=repuesto,
                    cantidad=dto.stock_inicial,
                    motivo="Stock inicial",
                    usuario_id=actor.id,
                )

            return armar_repuesto_response(repuesto)

    @staticmethod
    async def actualizar(
        repuesto_id: int,
        dto: RepuestoActualizarRequest,
        actor: UsuarioActual,
        uow: RepuestosUnitOfWork,
    ) -> RepuestoResponse:
        """Actualiza descripción y/o precio en un único Unit of Work (RN-20)."""
        async with uow:
            repuesto = await uow.repuestos.get_by_id(repuesto_id)
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado",
                )

            datos = dto.model_dump(exclude_unset=True)
            if datos.get("descripcion") is not None:
                repuesto.descripcion = datos["descripcion"]

            precio_nuevo: Decimal | None = datos.get("precio")
            if precio_nuevo is not None and precio_nuevo != repuesto.precio:
                precio_anterior = repuesto.precio
                repuesto.precio = precio_nuevo
                await uow.repuestos.update(repuesto)
                await uow.precios.add(
                    HistorialPrecioRepuesto(
                        repuesto_id=repuesto.id,
                        usuario_id=actor.id,
                        precio_anterior=precio_anterior,
                        precio_nuevo=precio_nuevo,
                    )
                )
            else:
                await uow.repuestos.update(repuesto)

            return armar_repuesto_response(repuesto)

    @staticmethod
    async def eliminar(
        repuesto_id: int,
        uow: RepuestosUnitOfWork,
    ) -> None:
        async with uow:
            repuesto = await uow.repuestos.get_by_id(repuesto_id)
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado",
                )
            await uow.repuestos.soft_delete(repuesto)

    @staticmethod
    async def reponer(
        repuesto_id: int,
        dto: ReponerStockRequest,
        actor: UsuarioActual,
        uow: RepuestosUnitOfWork,
    ) -> RepuestoResponse:
        """Repone stock usando el punto único de escritura (RN-14)."""
        async with uow:
            repuesto = await uow.repuestos.get_by_id(repuesto_id)
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado",
                )

            try:
                await uow.movimientos.registrar_movimiento(
                    repuesto=repuesto,
                    cantidad=dto.cantidad,
                    motivo="Reposición de stock",
                    usuario_id=actor.id,
                )
            except StockInsuficienteError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc

            return armar_repuesto_response(repuesto)

    @staticmethod
    async def listar_movimientos(
        repuesto_id: int,
        uow: RepuestosUnitOfWork,
    ) -> list[MovimientoStockResponse]:
        async with uow:
            repuesto = await uow.repuestos.get_by_id(repuesto_id)
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado",
                )
            movimientos = await uow.movimientos.listar_por_repuesto(repuesto_id)
            return [armar_movimiento_response(mov) for mov in movimientos]

    @staticmethod
    async def listar_precios(
        repuesto_id: int,
        uow: RepuestosUnitOfWork,
    ) -> list[HistorialPrecioResponse]:
        async with uow:
            repuesto = await uow.repuestos.get_by_id(repuesto_id)
            if repuesto is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Repuesto no encontrado",
                )
            historial = await uow.precios.listar_por_repuesto(repuesto_id)
            return [armar_historial_response(linea) for linea in historial]
