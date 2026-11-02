from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

T = TypeVar("T", bound=SQLModel)


class BaseRepository(Generic[T]):
    """Repositorio base genérico asincrónico para operaciones CRUD.

    Recibe explícitamente la sesión y la clase del modelo porque los genéricos
    se borran en tiempo de ejecución.

    Regla dura del proyecto (RN-15, DD-06):
    Llama exclusivamente a session.flush() y prohíbe absolutamente session.commit().
    El commit es responsabilidad exclusiva del Unit of Work.
    """

    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        # Compatibilidad: se acepta tanto (session, model) como (model, session).
        if isinstance(session, type) and model is not None:
            session, model = model, session  # type: ignore[assignment]
        self.session: AsyncSession = session
        self.model: type[T] = model

    async def get_by_id(self, id: Any) -> T | None:
        """Obtiene una entidad por su clave primaria."""
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> Sequence[T]:
        """Obtiene un conjunto de entidades ordenadas por paginación."""
        stmt = select(self.model).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Cuenta la cantidad total de entidades persistidas."""
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def add(self, entity: T) -> T:
        """Agrega una entidad a la sesión, ejecuta flush y refresca sus atributos generados."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: T) -> T:
        """Confirma los cambios en el búfer de la sesión con flush y refresca la entidad."""
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity: T) -> None:
        """Remueve físicamente la entidad de la base de datos y ejecuta flush."""
        await self.session.delete(entity)
        await self.session.flush()


class SoftDeleteRepository(BaseRepository[T]):
    """Repositorio base para entidades que implementan borrado lógico mediante borrado_en."""

    def __init__(self, session: AsyncSession, model: type[T] | None = None) -> None:
        super().__init__(session, model)  # type: ignore[arg-type]
        if not hasattr(self.model, "borrado_en"):
            raise TypeError(
                f"El modelo {self.model.__name__} no soporta borrado lógico "
                "(falta atributo borrado_en)"
            )

    async def get_by_id(self, id: Any) -> T | None:
        """Obtiene la entidad sólo si no ha sido borrada lógicamente."""
        stmt = select(self.model).where(
            self.model.id == id,
            self.model.borrado_en.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_including_deleted(self, id: Any) -> T | None:
        """Obtiene la entidad aunque esté dada de baja lógicamente."""
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> Sequence[T]:
        """Lista entidades activas ignorando aquellas con fecha de baja lógica."""
        stmt = select(self.model).where(self.model.borrado_en.is_(None)).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Cuenta exclusivamente las entidades activas no borradas."""
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.borrado_en.is_(None))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def soft_delete(self, entity_or_id: T | Any) -> T:
        """Establece borrado_en con la fecha actual y ejecuta flush en la sesión."""
        if isinstance(entity_or_id, self.model):
            entity = entity_or_id
        else:
            entity = await self.get_by_id(entity_or_id)
            if entity is None:
                raise ValueError(
                    f"No se encontró {self.model.__name__} activo con identificador {entity_or_id}"
                )

        entity.borrado_en = datetime.now(timezone.utc)
        await self.session.flush()
        return entity
