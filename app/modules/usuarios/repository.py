from datetime import datetime, timedelta, timezone
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import BaseRepository
from app.modules.usuarios.models import AsignacionRol, IntentoAcceso, Usuario


class UsuarioRepository(BaseRepository[Usuario]):
    """Repositorio para la entidad Usuario."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Usuario, session)

    async def get_by_email(self, email: str) -> Usuario | None:
        stmt = select(Usuario).where(Usuario.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class AsignacionRolRepository(BaseRepository[AsignacionRol]):
    """Repositorio para asignaciones de roles."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AsignacionRol, session)

    async def get_roles_vigentes(self, usuario_id: int) -> list[str]:
        """Consulta los roles vigentes en base de datos (RN-04)."""
        ahora = datetime.now(timezone.utc)
        stmt = select(AsignacionRol.rol).where(
            AsignacionRol.usuario_id == usuario_id,
            AsignacionRol.revocada_en.is_(None),
            or_(
                AsignacionRol.vence_en.is_(None),
                AsignacionRol.vence_en > ahora,
            ),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class IntentoAccesoRepository(BaseRepository[IntentoAcceso]):
    """Repositorio para auditoría de intentos de inicio de sesión."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(IntentoAcceso, session)

    async def contar_fallos_recientes(
        self,
        email: str,
        ip: str,
        ventana_segundos: int = 60,
    ) -> int:
        """Cuenta los intentos fallidos en los últimos N segundos (RN-08).

        Un login correcto reinicia la cuenta: sólo se cuentan los fallos
        posteriores al último acceso exitoso del par (email, ip).
        """
        ahora = datetime.now(timezone.utc)
        limite = ahora - timedelta(seconds=ventana_segundos)

        # Buscar el último intento exitoso para reiniciar el contador
        stmt_ultimo_exito = select(func.max(IntentoAcceso.cuando)).where(
            IntentoAcceso.email == email,
            IntentoAcceso.ip == ip,
            IntentoAcceso.exito.is_(True),
        )
        res_exito = await self.session.execute(stmt_ultimo_exito)
        ultimo_exito = res_exito.scalar_one_or_none()

        if ultimo_exito is not None and ultimo_exito > limite:
            limite = ultimo_exito

        stmt = (
            select(func.count())
            .select_from(IntentoAcceso)
            .where(
                IntentoAcceso.email == email,
                IntentoAcceso.ip == ip,
                IntentoAcceso.exito.is_(False),
                IntentoAcceso.cuando > limite,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
