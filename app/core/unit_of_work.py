from types import TracebackType
from typing import Self
from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    """Gestor de contexto asincrónico para transacciones atómicas.

    Regla dura de diseño (DD-06):
    - Confirma (commit) automáticamente si el bloque finaliza sin excepciones.
    - Revierte (rollback) automáticamente si se produce cualquier excepción.
    - No cierra la sesión de base de datos (su ciclo de vida es gestionado por FastAPI/lifespan).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if exc_type is not None:
            await self.rollback()
            return False  # Propaga la excepción original
        await self.commit()
        return True

    async def commit(self) -> None:
        """Confirma los cambios pendientes de la transacción."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Revierte cualquier modificación no confirmada en la sesión."""
        await self.session.rollback()
