from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import (
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)


class EstadoOrdenRepository:
    """Repositorio de sólo lectura del catálogo de estados.

    No hereda de BaseRepository a propósito: su clave primaria no es `id` y la
    API no debe ofrecer add, update ni delete sobre el catálogo (RN-19).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def listar_por_posicion(self) -> Sequence[EstadoOrden]:
        stmt = select(EstadoOrden).order_by(EstadoOrden.posicion)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_codigo(self, codigo: str) -> EstadoOrden | None:
        stmt = select(EstadoOrden).where(EstadoOrden.codigo == codigo)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def contar(self) -> int:
        stmt = select(func.count()).select_from(EstadoOrden)
        result = await self.session.execute(stmt)
        return result.scalar_one()


class OrdenTrabajoRepository(BaseRepository[OrdenTrabajo]):
    """Repositorio para la entidad OrdenTrabajo."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OrdenTrabajo)

    async def get_detalle(self, orden_id: int) -> OrdenTrabajo | None:
        """Obtiene la orden con vehículo, cliente, ítems, repuestos e historial.

        La precarga se declara acá, dentro del método que la necesita (sin N+1).
        """
        stmt = (
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == orden_id)
            .options(
                selectinload(OrdenTrabajo.vehiculo).selectinload(Vehiculo.cliente),
                selectinload(OrdenTrabajo.items).selectinload(ItemOrden.repuesto),
                selectinload(OrdenTrabajo.historial_estados),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def listar(
        self,
        estado: str | None,
        offset: int = 0,
        limit: int | None = None,
    ) -> Sequence[OrdenTrabajo]:
        stmt = select(OrdenTrabajo).options(selectinload(OrdenTrabajo.vehiculo))
        if estado:
            stmt = stmt.where(OrdenTrabajo.estado == estado)
        stmt = stmt.order_by(OrdenTrabajo.id.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def contar_por_estado(self, estado: str | None) -> int:
        stmt = select(func.count()).select_from(OrdenTrabajo)
        if estado:
            stmt = stmt.where(OrdenTrabajo.estado == estado)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def contar_ordenes_abiertas(self, vehiculo_id: int) -> int:
        """Cuenta órdenes del vehículo en estados que el catálogo no marca finales (RN-16)."""
        stmt = (
            select(func.count())
            .select_from(OrdenTrabajo)
            .join(EstadoOrden, OrdenTrabajo.estado == EstadoOrden.codigo)
            .where(
                OrdenTrabajo.vehiculo_id == vehiculo_id,
                EstadoOrden.es_final.is_(False),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def listar_por_cliente_usuario(
        self,
        usuario_id: int,
        offset: int = 0,
        limit: int | None = None,
    ) -> Sequence[OrdenTrabajo]:
        """Lista las órdenes de los vehículos del cliente autenticado (RN-17)."""
        stmt = (
            select(OrdenTrabajo)
            .join(Vehiculo, OrdenTrabajo.vehiculo_id == Vehiculo.id)
            .join(Cliente, Vehiculo.cliente_id == Cliente.id)
            .where(Cliente.usuario_id == usuario_id)
            .options(selectinload(OrdenTrabajo.vehiculo))
            .order_by(OrdenTrabajo.id.desc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def contar_por_cliente_usuario(self, usuario_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(OrdenTrabajo)
            .join(Vehiculo, OrdenTrabajo.vehiculo_id == Vehiculo.id)
            .join(Cliente, Vehiculo.cliente_id == Cliente.id)
            .where(Cliente.usuario_id == usuario_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()


class ItemOrdenRepository(BaseRepository[ItemOrden]):
    """Repositorio para la entidad ItemOrden."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ItemOrden)

    async def listar_por_orden(self, orden_id: int) -> Sequence[ItemOrden]:
        stmt = (
            select(ItemOrden)
            .where(ItemOrden.orden_id == orden_id)
            .order_by(ItemOrden.id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class HistorialEstadoOrdenRepository(BaseRepository[HistorialEstadoOrden]):
    """Repositorio del historial de estados (sólo agregado)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HistorialEstadoOrden)

    async def listar_por_orden(self, orden_id: int) -> Sequence[HistorialEstadoOrden]:
        stmt = (
            select(HistorialEstadoOrden)
            .where(HistorialEstadoOrden.orden_id == orden_id)
            .order_by(HistorialEstadoOrden.cuando, HistorialEstadoOrden.id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
