from typing import Any
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import crear_access_token, hash_password, verify_password
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import AsignacionRol, IntentoAcceso, Usuario
from app.modules.usuarios.repository import (
    AsignacionRolRepository,
    IntentoAccesoRepository,
    UsuarioRepository,
)
from app.modules.usuarios.schemas import RegistroClienteRequest
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork


class AuthService:
    """Servicio de autenticación y auto-registro."""

    @staticmethod
    async def registrar_cliente(
        dto: RegistroClienteRequest,
        uow: UsuariosUnitOfWork,
    ) -> tuple[Usuario, list[str], int]:
        """Crea atómicamente Usuario + Rol CLIENTE + Cliente en un único UoW (RN-02).

        Retorna (usuario, roles, cliente_id).
        Lanza HTTPException(409) si email o documento ya existen.
        """
        async with uow:
            existente_email = await uow.usuarios.get_by_email(dto.email)
            if existente_email is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El correo ya se encuentra registrado",
                )

            existente_doc = await uow.clientes.get_by_documento(dto.documento)
            if existente_doc is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El documento ya pertenece a un cliente del taller",
                )

            pwd_hash = await hash_password(dto.password)
            usuario = Usuario(
                email=dto.email,
                nombre=dto.nombre,
                password_hash=pwd_hash,
                activo=True,
                debe_cambiar_password=False,
            )
            usuario = await uow.usuarios.add(usuario)

            rol = AsignacionRol(usuario_id=usuario.id, rol="CLIENTE")
            await uow.roles.add(rol)

            cliente = Cliente(
                usuario_id=usuario.id,
                nombre=dto.nombre,
                documento=dto.documento,
                telefono=dto.telefono,
            )
            cliente = await uow.clientes.add(cliente)

        return usuario, ["CLIENTE"], cliente.id

    @staticmethod
    async def login(
        email: str,
        password: str,
        ip: str,
        app_state_or_dummy_hash: Any,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> tuple[Usuario, str, list[str]]:
        """Inicia sesión con rate-limit (RN-08) y timing defense (RN-09).

        DD-04: El intento de acceso se audita en una sesión independiente.
        Retorna (usuario, token, roles).
        """
        # 1. Resolver dummy_hash
        if hasattr(app_state_or_dummy_hash, "dummy_hash"):
            dummy_hash = app_state_or_dummy_hash.dummy_hash
        elif isinstance(app_state_or_dummy_hash, str):
            dummy_hash = app_state_or_dummy_hash
        else:
            dummy_hash = getattr(app_state_or_dummy_hash, "dummy_hash", None)

        if not dummy_hash:
            from app.core.config import get_settings
            import bcrypt
            settings = get_settings()
            dummy_hash = bcrypt.hashpw(b"dummy_pass", bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode("utf-8")

        # 2. Conteo de fallos en sesión independiente (RN-08)
        async with session_factory() as session_rl:
            repo_intentos = IntentoAccesoRepository(session_rl)
            fallos_recientes = await repo_intentos.contar_fallos_recientes(email, ip, ventana_segundos=60)
            if fallos_recientes >= 5:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Demasiados intentos fallidos. Intente nuevamente en 60 segundos.",
                    headers={"Retry-After": "60"},
                )

        # 3. Búsqueda de usuario y verificación timing-safe (RN-09)
        async with session_factory() as session_auth:
            repo_usr = UsuarioRepository(session_auth)
            repo_roles = AsignacionRolRepository(session_auth)
            usuario = await repo_usr.get_by_email(email)

            if usuario is not None and usuario.activo:
                target_hash = usuario.password_hash
            else:
                target_hash = dummy_hash

            pwd_valida = await verify_password(password, target_hash)
            exito = bool(pwd_valida and usuario is not None and usuario.activo)

            if exito:
                roles = await repo_roles.get_roles_vigentes(usuario.id)
            else:
                roles = []

        # 4. Registrar intento en sesión independiente con commit garantizado (DD-04)
        async with session_factory() as session_audit:
            intento = IntentoAcceso(email=email, ip=ip, exito=exito)
            session_audit.add(intento)
            await session_audit.commit()

        # 5. Si falló, emitir 401 uniforme
        if not exito:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas",
            )

        # 6. Éxito: emitir JWT
        token = crear_access_token(
            {
                "sub": usuario.email,
                "user_id": usuario.id,
                "roles": roles,
            }
        )
        return usuario, token, roles
