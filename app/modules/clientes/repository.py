from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.clientes.models import Cliente, Vehiculo


class ClienteRepository(BaseRepository[Cliente]):
    """Repositorio para la entidad Cliente."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Cliente)

    async def get_by_documento(self, documento: str) -> Cliente | None:
        stmt = select(Cliente).where(Cliente.documento == documento)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_usuario_id(self, usuario_id: int) -> Cliente | None:
        stmt = select(Cliente).where(Cliente.usuario_id == usuario_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_con_vehiculos(self, cliente_id: int) -> Cliente | None:
        """Obtiene el cliente precargando sus vehículos vigentes (RN-16)."""
        stmt = (
            select(Cliente)
            .where(Cliente.id == cliente_id)
            .options(selectinload(Cliente.vehiculos.and_(Vehiculo.borrado_en.is_(None))))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class VehiculoRepository(SoftDeleteRepository[Vehiculo]):
    """Repositorio para la entidad Vehiculo con borrado lógico."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Vehiculo)

    async def get_by_patente(self, patente: str) -> Vehiculo | None:
        """Busca un vehículo vigente por patente (RN-01, RN-16)."""
        stmt = select(Vehiculo).where(
            Vehiculo.patente == patente,
            Vehiculo.borrado_en.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def listar_por_cliente(self, cliente_id: int) -> Sequence[Vehiculo]:
        """Lista los vehículos vigentes de un cliente (RN-16, RN-17)."""
        stmt = (
            select(Vehiculo)
            .where(
                Vehiculo.cliente_id == cliente_id,
                Vehiculo.borrado_en.is_(None),
            )
            .order_by(Vehiculo.id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_id_con_ordenes(self, vehiculo_id: int) -> Vehiculo | None:
        """Obtiene el vehículo precargando sus órdenes de trabajo."""
        stmt = (
            select(Vehiculo)
            .where(
                Vehiculo.id == vehiculo_id,
                Vehiculo.borrado_en.is_(None),
            )
            .options(selectinload(Vehiculo.ordenes))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_con_cliente(self, vehiculo_id: int) -> Vehiculo | None:
        """Obtiene el vehículo vigente precargando su cliente."""
        stmt = (
            select(Vehiculo)
            .where(
                Vehiculo.id == vehiculo_id,
                Vehiculo.borrado_en.is_(None),
            )
            .options(selectinload(Vehiculo.cliente))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
