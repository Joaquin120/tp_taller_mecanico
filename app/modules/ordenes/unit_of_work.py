"""Unit of Work del módulo de órdenes de trabajo.

Comparte una única `AsyncSession` entre el catálogo de estados, las órdenes,
sus ítems, el historial, los vehículos (C-06), los repuestos y los movimientos
de stock (C-07). Ningún repositorio hace `commit()`: lo hace el UoW.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import VehiculoRepository
from app.modules.ordenes.repository import (
    EstadoOrdenRepository,
    HistorialEstadoOrdenRepository,
    ItemOrdenRepository,
    OrdenTrabajoRepository,
)
from app.modules.repuestos.repository import (
    MovimientoStockRepository,
    RepuestoRepository,
)


class OrdenesUnitOfWork(UnitOfWork):
    """Agrupa los siete repositorios del ciclo de vida de una orden."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.estados = EstadoOrdenRepository(session)
        self.ordenes = OrdenTrabajoRepository(session)
        self.items = ItemOrdenRepository(session)
        self.historial = HistorialEstadoOrdenRepository(session)
        self.vehiculos = VehiculoRepository(session)
        self.repuestos = RepuestoRepository(session)
        self.movimientos = MovimientoStockRepository(session)
