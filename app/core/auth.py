from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request, status
import jwt
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decodificar_access_token
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import AsignacionRol, Usuario


class UsuarioActual(BaseModel):
    """Representa el usuario autenticado con sus roles vigentes de base de datos."""

    model_config = ConfigDict(extra="forbid")

    id: int
    email: str
    nombre: str
    activo: bool
    debe_cambiar_password: bool
    roles: list[str]
    roles_token: list[str] = []
    cliente_id: int | None = None


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UsuarioActual:
    """Extrae el token JWT de la cookie HttpOnly y verifica roles frescos en la base de datos.

    Reglas duras:
    - DD-02: Lee exclusivamente la cookie 'access_token'.
    - RN-04: Consulta en la base de datos los roles vigentes en cada petición.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado: cookie de acceso ausente",
        )

    try:
        payload = decodificar_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada: token caducado",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o malformado",
        )

    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: sin identificador de usuario",
        )

    # 1. Obtener usuario activo
    stmt_user = select(Usuario).where(Usuario.email == email)
    res_user = await session.execute(stmt_user)
    user = res_user.scalar_one_or_none()

    if user is None or not user.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo",
        )

    # 2. Invalidar sesiones anteriores al último cambio de contraseña (RN-07)
    if user.password_cambiada_en is not None:
        iat = payload.get("iat")
        if not isinstance(iat, (int, float)) or isinstance(iat, bool):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: sin fecha de emisión",
            )

        referencia = user.password_cambiada_en
        if referencia.tzinfo is None:
            referencia = referencia.replace(tzinfo=timezone.utc)

        if float(iat) < referencia.timestamp():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sesión invalidada por cambio de contraseña",
            )

    # 3. Consultar roles vigentes en BD (RN-04)
    ahora = datetime.now(timezone.utc)
    stmt_roles = select(AsignacionRol.rol).where(
        AsignacionRol.usuario_id == user.id,
        AsignacionRol.revocada_en.is_(None),
        or_(
            AsignacionRol.vence_en.is_(None),
            AsignacionRol.vence_en > ahora,
        ),
    )
    res_roles = await session.execute(stmt_roles)
    roles_vigentes = list(res_roles.scalars().all())

    # 4. Buscar cliente_id si existe
    stmt_cliente = select(Cliente.id).where(Cliente.usuario_id == user.id)
    res_cliente = await session.execute(stmt_cliente)
    cliente_id = res_cliente.scalar_one_or_none()

    roles_token = payload.get("roles", [])

    return UsuarioActual(
        id=user.id,
        email=user.email,
        nombre=user.nombre,
        activo=user.activo,
        debe_cambiar_password=user.debe_cambiar_password,
        roles=roles_vigentes,
        roles_token=roles_token,
        cliente_id=cliente_id,
    )


def require_roles(*roles_permitidos: str):
    """Genera una dependencia FastAPI que verifica que el usuario posea al menos uno de los roles."""

    async def _role_checker(
        usuario: UsuarioActual = Depends(get_current_user),
    ) -> UsuarioActual:
        if not any(rol in usuario.roles for rol in roles_permitidos):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permisos insuficientes para realizar esta acción",
            )
        return usuario

    return _role_checker


async def requiere_password_actualizada(
    usuario: UsuarioActual = Depends(get_current_user),
) -> UsuarioActual:
    """Bloquea el grupo protegido mientras el cambio de contraseña esté pendiente (RN-06)."""

    if usuario.debe_cambiar_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debe cambiar su contraseña antes de continuar",
        )
    return usuario


# Alias en español para respetar nomenclatura canónica del proyecto
get_usuario_actual = get_current_user
requiere_rol = require_roles
