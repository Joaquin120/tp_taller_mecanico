from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import BaseRepository
from app.modules.clientes.models import Cliente


class ClienteRepository(BaseRepository[Cliente]):
    """Repositorio para la entidad Cliente."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Cliente, session)

    async def get_by_documento(self, documento: str) -> Cliente | None:
        stmt = select(Cliente).where(Cliente.documento == documento)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_usuario_id(self, usuario_id: int) -> Cliente | None:
        stmt = select(Cliente).where(Cliente.usuario_id == usuario_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
