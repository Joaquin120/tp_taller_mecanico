"""Repositorios del módulo de órdenes de trabajo.

Reglas duras:
- Sólo se llama a `session.flush()`; nunca a `session.commit()` (lo hace el UoW).
- El detalle usa carga anticipada fija (`selectinload`) para garantizar cero N+1.
- `historial_estado_orden` es de sólo agregado: su repositorio expone `add` y
  consultas, y bloquea `update`/`delete`.
- `estado_orden` es un catálogo de sólo lectura: no hereda de `BaseRepository`
  porque su PK no es `id` y no debe ofrecer escrituras.
"""

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
    """Repositorio de sólo lectura del catálogo de estados (RN-19)."""

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


def _opciones_detalle() -> tuple:
    """Opciones de carga anticipada fijas: constantes respecto del nº de ítems."""
    return (
        selectinload(OrdenTrabajo.vehiculo).selectinload(Vehiculo.cliente),
        selectinload(OrdenTrabajo.items).selectinload(ItemOrden.repuesto),
        selectinload(OrdenTrabajo.historial_estados),
        selectinload(OrdenTrabajo.mecanico),
    )


class OrdenTrabajoRepository(BaseRepository[OrdenTrabajo]):
    """Repositorio para la entidad OrdenTrabajo."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OrdenTrabajo)

    async def get_detalle(self, orden_id: int) -> OrdenTrabajo | None:
        """Obtiene la orden con vehículo, cliente, ítems, repuestos e historial.

        La precarga se declara acá, dentro del método que la necesita, y usa
        `selectinload`: una consulta por relación sin importar la cantidad de
        ítems (cero N+1).
        """
        stmt = (
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == orden_id)
            .options(*_opciones_detalle())
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_para_actualizar(self, orden_id: int) -> OrdenTrabajo | None:
        """Obtiene el detalle bloqueando la fila de la orden para mutaciones.

        El bloqueo evita que dos terminaciones concurrentes descuenten stock dos
        veces; las relaciones se precargan antes de mutar el estado.
        """
        stmt = (
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == orden_id)
            .options(*_opciones_detalle())
            .with_for_update()
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


class HistorialEstadoOrdenRepository(_SoloAgregadoRepository):
    """Historial de estados de la orden: sólo inserciones y consultas."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(HistorialEstadoOrden, session)

    async def listar_por_orden(
        self,
        orden_id: int,
    ) -> Sequence[HistorialEstadoOrden]:
        stmt = (
            select(HistorialEstadoOrden)
            .where(HistorialEstadoOrden.orden_id == orden_id)
            .order_by(
                HistorialEstadoOrden.cuando,
                HistorialEstadoOrden.id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
