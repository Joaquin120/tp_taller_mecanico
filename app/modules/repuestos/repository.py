"""Repositorios del módulo de repuestos.

Reglas duras:
- Sólo se llama a `session.flush()`; nunca a `session.commit()` (lo hace el UoW).
- `movimiento_stock` e `historial_precio_repuesto` son de sólo agregado: sus
  repositorios exponen inserciones y consultas, y bloquean `update`/`delete`.
"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)


class RepuestoRepository(SoftDeleteRepository[Repuesto]):
    """Repositorio de repuestos con filtrado de borrado lógico."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Repuesto, session)

    async def get_by_codigo_vigente(self, codigo: str) -> Repuesto | None:
        """Busca un repuesto vigente por código (índice único parcial)."""
        stmt = select(Repuesto).where(
            Repuesto.codigo == codigo,
            Repuesto.borrado_en.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def listar_paginado(
        self,
        q: str | None,
        offset: int,
        limit: int,
    ) -> Sequence[Repuesto]:
        """Lista repuestos vigentes, filtrando por descripción y ordenando por código."""
        stmt = select(Repuesto).where(Repuesto.borrado_en.is_(None))
        if q:
            stmt = stmt.where(Repuesto.descripcion.ilike(f"%{q}%"))
        stmt = stmt.order_by(Repuesto.codigo.asc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def contar_vigentes(self, q: str | None) -> int:
        """Cuenta repuestos vigentes con el mismo filtro que `listar_paginado`."""
        stmt = (
            select(func.count())
            .select_from(Repuesto)
            .where(Repuesto.borrado_en.is_(None))
        )
        if q:
            stmt = stmt.where(Repuesto.descripcion.ilike(f"%{q}%"))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_para_actualizar(self, id: int) -> Repuesto | None:
        """Obtiene un repuesto vigente bloqueando la fila para mutaciones atómicas."""
        stmt = (
            select(Repuesto)
            .where(Repuesto.id == id, Repuesto.borrado_en.is_(None))
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class _SoloAgregadoRepository(BaseRepository):
    """Base de repositorios inmutables: permite insertar y consultar, nada más."""

    async def update(self, entity):  # type: ignore[override]
        raise NotImplementedError(
            f"{self.model.__name__} es de sólo agregado: no admite update"
        )

    async def delete(self, entity):  # type: ignore[override]
        raise NotImplementedError(
            f"{self.model.__name__} es de sólo agregado: no admite delete"
        )


class MovimientoStockRepository(_SoloAgregadoRepository):
    """Historial de movimientos de stock: sólo inserciones y consultas."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MovimientoStock, session)

    async def listar_por_repuesto(
        self,
        repuesto_id: int,
        offset: int,
        limit: int,
    ) -> Sequence[MovimientoStock]:
        stmt = (
            select(MovimientoStock)
            .where(MovimientoStock.repuesto_id == repuesto_id)
            .order_by(MovimientoStock.cuando.desc(), MovimientoStock.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def contar_por_repuesto(self, repuesto_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(MovimientoStock)
            .where(MovimientoStock.repuesto_id == repuesto_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()


class HistorialPrecioRepuestoRepository(_SoloAgregadoRepository):
    """Historial de precios: sólo inserciones y consultas."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(HistorialPrecioRepuesto, session)

    async def listar_por_repuesto(
        self,
        repuesto_id: int,
        offset: int,
        limit: int,
    ) -> Sequence[HistorialPrecioRepuesto]:
        stmt = (
            select(HistorialPrecioRepuesto)
            .where(HistorialPrecioRepuesto.repuesto_id == repuesto_id)
            .order_by(
                HistorialPrecioRepuesto.cuando.desc(),
                HistorialPrecioRepuesto.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def contar_por_repuesto(self, repuesto_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(HistorialPrecioRepuesto)
            .where(HistorialPrecioRepuesto.repuesto_id == repuesto_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
