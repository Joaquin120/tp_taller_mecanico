from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository, VehiculoRepository
from app.modules.ordenes.repository import OrdenTrabajoRepository


class ClientesUnitOfWork(UnitOfWork):
    """Unit of Work del módulo de clientes y vehículos."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.clientes = ClienteRepository(session)
        self.vehiculos = VehiculoRepository(session)
        self.ordenes = OrdenTrabajoRepository(session)
