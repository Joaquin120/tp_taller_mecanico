from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)


class StockInsuficienteError(Exception):
    """El stock disponible no alcanza para registrar una salida."""


class RepuestoRepository(SoftDeleteRepository[Repuesto]):
    """Repositorio para la entidad Repuesto con borrado lógico."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Repuesto)

    async def get_by_codigo(self, codigo: str) -> Repuesto | None:
        """Busca un repuesto vigente por código (RN-01)."""
        stmt = select(Repuesto).where(
            Repuesto.codigo == codigo,
            Repuesto.borrado_en.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def buscar_por_descripcion(
        self,
        descripcion: str | None,
        offset: int = 0,
        limit: int | None = None,
    ) -> Sequence[Repuesto]:
        """Busca repuestos vigentes por descripción con parámetro ligado."""
        stmt = select(Repuesto).where(Repuesto.borrado_en.is_(None))
        if descripcion:
            stmt = stmt.where(Repuesto.descripcion.ilike(f"%{descripcion}%"))
        stmt = stmt.order_by(Repuesto.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def contar_por_descripcion(self, descripcion: str | None) -> int:
        """Cuenta repuestos vigentes aplicando el mismo filtro que el listado."""
        stmt = (
            select(func.count())
            .select_from(Repuesto)
            .where(Repuesto.borrado_en.is_(None))
        )
        if descripcion:
            stmt = stmt.where(Repuesto.descripcion.ilike(f"%{descripcion}%"))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_by_id_con_movimientos(self, repuesto_id: int) -> Repuesto | None:
        """Obtiene el repuesto precargando sus movimientos de stock."""
        stmt = (
            select(Repuesto)
            .where(
                Repuesto.id == repuesto_id,
                Repuesto.borrado_en.is_(None),
            )
            .options(selectinload(Repuesto.movimientos))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_con_historial_precios(
        self, repuesto_id: int
    ) -> Repuesto | None:
        """Obtiene el repuesto precargando su historial de precios."""
        stmt = (
            select(Repuesto)
            .where(
                Repuesto.id == repuesto_id,
                Repuesto.borrado_en.is_(None),
            )
            .options(selectinload(Repuesto.historial_precios))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class MovimientoStockRepository(BaseRepository[MovimientoStock]):
    """Repositorio de movimientos de stock.

    `registrar_movimiento` es el ÚNICO punto de escritura del stock (RN-14):
    lo usan tanto la reposición como la terminación de órdenes de trabajo.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MovimientoStock)

    async def listar_por_repuesto(self, repuesto_id: int) -> Sequence[MovimientoStock]:
        stmt = (
            select(MovimientoStock)
            .where(MovimientoStock.repuesto_id == repuesto_id)
            .order_by(MovimientoStock.cuando, MovimientoStock.id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def registrar_movimiento(
        self,
        *,
        repuesto: Repuesto,
        cantidad: int,
        motivo: str,
        usuario_id: int,
        orden_id: int | None = None,
    ) -> MovimientoStock:
        """Punto único de escritura de stock (RN-14).

        Actualiza el stock del repuesto e inserta el movimiento en la misma
        transacción. Una cantidad positiva repone stock; una negativa lo descuenta.
        """
        if cantidad == 0:
            raise ValueError("La cantidad de un movimiento de stock no puede ser cero")

        nuevo_stock = repuesto.stock + cantidad
        if nuevo_stock < 0:
            raise StockInsuficienteError(
                f"Stock insuficiente para el repuesto {repuesto.id}: "
                f"disponible {repuesto.stock}, solicitado {-cantidad}"
            )

        repuesto.stock = nuevo_stock
        movimiento = MovimientoStock(
            repuesto_id=repuesto.id,
            orden_id=orden_id,
            usuario_id=usuario_id,
            cantidad=cantidad,
            motivo=motivo,
        )
        self.session.add(movimiento)
        await self.session.flush()
        return movimiento


class HistorialPrecioRepuestoRepository(BaseRepository[HistorialPrecioRepuesto]):
    """Repositorio del historial de precios (sólo agregado)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HistorialPrecioRepuesto)

    async def listar_por_repuesto(
        self, repuesto_id: int
    ) -> Sequence[HistorialPrecioRepuesto]:
        stmt = (
            select(HistorialPrecioRepuesto)
            .where(HistorialPrecioRepuesto.repuesto_id == repuesto_id)
            .order_by(
                HistorialPrecioRepuesto.cuando,
                HistorialPrecioRepuesto.id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
