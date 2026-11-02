"""Unit of Work del módulo de repuestos."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.repuestos.repository import (
    HistorialPrecioRepuestoRepository,
    MovimientoStockRepository,
    RepuestoRepository,
)


class RepuestosUnitOfWork(UnitOfWork):
    """Agrupa repuestos, movimientos e historial de precios en una sola transacción."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repuestos = RepuestoRepository(session)
        self.movimientos = MovimientoStockRepository(session)
        self.precios = HistorialPrecioRepuestoRepository(session)
