"""Servicios del catálogo de repuestos.

Reglas de negocio aplicadas:
- RN-14: el stock sólo cambia por alta con stock inicial o reposición; nunca por PATCH.
- RN-20: cada cambio de precio deja una fila en `historial_precio_repuesto` en el
  mismo UoW; un precio idéntico no genera fila.
- Las tablas de historial son de sólo agregado: el servicio únicamente inserta.
"""

from fastapi import HTTPException, status

from app.core.auth import UsuarioActual
from app.core.paginacion import PaginatedResponse, armar_paginacion
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.repuestos.schemas import (
    HistorialPrecioResponse,
    MovimientoStockResponse,
    ReponerStockRequest,
    RepuestoCreate,
    RepuestoResponse,
    RepuestoUpdate,
)
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork

MOTIVO_ALTA = "ALTA"
MOTIVO_REPOSICION = "REPOSICION"


def _a_response(repuesto: Repuesto) -> RepuestoResponse:
    return RepuestoResponse(
        id=repuesto.id,
        codigo=repuesto.codigo,
        descripcion=repuesto.descripcion,
        precio=repuesto.precio,
        stock=repuesto.stock,
    )


def _no_encontrado() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Repuesto no encontrado",
    )


class CatalogoService:
    """Casos de uso del catálogo, stock y precios."""

    @staticmethod
    async def listar(
        q: str | None,
        page: int,
        size: int,
        uow: RepuestosUnitOfWork,
    ) -> PaginatedResponse[RepuestoResponse]:
        """Lista repuestos vigentes con búsqueda por descripción y paginación."""
        async with uow:
            total = await uow.repuestos.contar_vigentes(q)
            filas = await uow.repuestos.listar_paginado(
                q=q,
                offset=(page - 1) * size,
                limit=size,
            )

        items = [_a_response(repuesto) for repuesto in filas]
        return armar_paginacion(items, total, page, size)

    @staticmethod
    async def obtener(id: int, uow: RepuestosUnitOfWork) -> RepuestoResponse:
        """Devuelve un repuesto vigente o 404."""
        async with uow:
            repuesto = await uow.repuestos.get_by_id(id)
            if repuesto is None:
                raise _no_encontrado()
        return _a_response(repuesto)

    @staticmethod
    async def crear(
        dto: RepuestoCreate,
        actor: UsuarioActual,
        uow: RepuestosUnitOfWork,
    ) -> RepuestoResponse:
        """Crea el repuesto y, si hay stock inicial, su movimiento de alta."""
        async with uow:
            existente = await uow.repuestos.get_by_codigo_vigente(dto.codigo)
            if existente is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El código de repuesto ya se encuentra registrado",
                )

            repuesto = Repuesto(
                codigo=dto.codigo,
                descripcion=dto.descripcion,
                precio=dto.precio,
                stock=dto.stock_inicial,
            )
            repuesto = await uow.repuestos.add(repuesto)

            if dto.stock_inicial > 0:
                await uow.movimientos.add(
                    MovimientoStock(
                        repuesto_id=repuesto.id,
                        usuario_id=actor.id,
                        cantidad=dto.stock_inicial,
                        motivo=MOTIVO_ALTA,
                        orden_id=None,
                    )
                )

        return _a_response(repuesto)

    @staticmethod
    async def actualizar(
        id: int,
        dto: RepuestoUpdate,
        actor: UsuarioActual,
        uow: RepuestosUnitOfWork,
    ) -> RepuestoResponse:
        """Actualiza descripción y/o precio; registra historial sólo si el precio cambia."""
        async with uow:
            repuesto = await uow.repuestos.get_para_actualizar(id)
            if repuesto is None:
                raise _no_encontrado()

            precio_anterior = repuesto.precio

            if dto.descripcion is not None:
                repuesto.descripcion = dto.descripcion

            precio_cambia = dto.precio is not None and dto.precio != precio_anterior
            if precio_cambia:
                repuesto.precio = dto.precio
                await uow.precios.add(
                    HistorialPrecioRepuesto(
                        repuesto_id=repuesto.id,
                        usuario_id=actor.id,
                        precio_anterior=precio_anterior,
                        precio_nuevo=dto.precio,
                    )
                )

            if dto.descripcion is not None or precio_cambia:
                repuesto = await uow.repuestos.update(repuesto)

        return _a_response(repuesto)

    @staticmethod
    async def reponer(
        id: int,
        dto: ReponerStockRequest,
        actor: UsuarioActual,
        uow: RepuestosUnitOfWork,
    ) -> RepuestoResponse:
        """Incrementa el stock y registra el movimiento de reposición en el mismo UoW."""
        async with uow:
            repuesto = await uow.repuestos.get_para_actualizar(id)
            if repuesto is None:
                raise _no_encontrado()

            repuesto.stock += dto.cantidad
            repuesto = await uow.repuestos.update(repuesto)
            await uow.movimientos.add(
                MovimientoStock(
                    repuesto_id=repuesto.id,
                    usuario_id=actor.id,
                    cantidad=dto.cantidad,
                    motivo=MOTIVO_REPOSICION,
                    orden_id=None,
                )
            )

        return _a_response(repuesto)

    @staticmethod
    async def dar_de_baja(id: int, uow: RepuestosUnitOfWork) -> None:
        """Aplica borrado lógico; el código queda libre por el índice parcial."""
        async with uow:
            repuesto = await uow.repuestos.get_by_id(id)
            if repuesto is None:
                raise _no_encontrado()
            await uow.repuestos.soft_delete(repuesto)

    @staticmethod
    async def listar_movimientos(
        id: int,
        page: int,
        size: int,
        uow: RepuestosUnitOfWork,
    ) -> PaginatedResponse[MovimientoStockResponse]:
        """Historial de movimientos del repuesto, del más reciente al más antiguo."""
        async with uow:
            repuesto = await uow.repuestos.get_by_id(id)
            if repuesto is None:
                raise _no_encontrado()
            total = await uow.movimientos.contar_por_repuesto(id)
            filas = await uow.movimientos.listar_por_repuesto(
                id,
                offset=(page - 1) * size,
                limit=size,
            )

        items = [
            MovimientoStockResponse(
                id=movimiento.id,
                cantidad=movimiento.cantidad,
                motivo=movimiento.motivo,
                cuando=movimiento.cuando,
                usuario_id=movimiento.usuario_id,
                orden_id=movimiento.orden_id,
            )
            for movimiento in filas
        ]
        return armar_paginacion(items, total, page, size)

    @staticmethod
    async def listar_precios(
        id: int,
        page: int,
        size: int,
        uow: RepuestosUnitOfWork,
    ) -> PaginatedResponse[HistorialPrecioResponse]:
        """Historial de cambios de precio, del más reciente al más antiguo."""
        async with uow:
            repuesto = await uow.repuestos.get_by_id(id)
            if repuesto is None:
                raise _no_encontrado()
            total = await uow.precios.contar_por_repuesto(id)
            filas = await uow.precios.listar_por_repuesto(
                id,
                offset=(page - 1) * size,
                limit=size,
            )

        items = [
            HistorialPrecioResponse(
                id=registro.id,
                precio_anterior=registro.precio_anterior,
                precio_nuevo=registro.precio_nuevo,
                cuando=registro.cuando,
                usuario_id=registro.usuario_id,
            )
            for registro in filas
        ]
        return armar_paginacion(items, total, page, size)
