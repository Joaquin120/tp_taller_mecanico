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
    """Unit of Work del módulo de órdenes de trabajo."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.ordenes = OrdenTrabajoRepository(session)
        self.items = ItemOrdenRepository(session)
        self.historial = HistorialEstadoOrdenRepository(session)
        self.estados = EstadoOrdenRepository(session)
        self.repuestos = RepuestoRepository(session)
        self.movimientos = MovimientoStockRepository(session)
        self.vehiculos = VehiculoRepository(session)
