from datetime import datetime, timezone
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import UsuarioActual
from app.core.paginacion import PaginatedResponse, armar_paginacion
from app.core.security import crear_access_token, hash_password, verify_password
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import AsignacionRol, EventoSeguridad, IntentoAcceso, Usuario
from app.modules.usuarios.repository import (
    AsignacionRolRepository,
    IntentoAccesoRepository,
    UsuarioRepository,
)
from app.modules.usuarios.schemas import (
    AsignacionRolResponse,
    AsignarRolRequest,
    CambiarPasswordRequest,
    CrearUsuarioRequest,
    EventoSeguridadResponse,
    RegistroClienteRequest,
)
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork

ACCION_ALTA_USUARIO = "ALTA_USUARIO"
ACCION_ASIGNACION_ROL = "ASIGNACION_ROL"
ACCION_REVOCACION_ROL = "REVOCACION_ROL"
ACCION_CAMBIO_PASSWORD = "CAMBIO_PASSWORD"


def _es_vigente(asignacion: AsignacionRol, ahora: datetime) -> bool:
    return asignacion.revocada_en is None and (
        asignacion.vence_en is None or asignacion.vence_en > ahora
    )


def armar_asignacion_response(asignacion: AsignacionRol, ahora: datetime | None = None) -> AsignacionRolResponse:
    if ahora is None:
        ahora = datetime.now(timezone.utc)
    return AsignacionRolResponse(
        id=asignacion.id,
        usuario_id=asignacion.usuario_id,
        rol=asignacion.rol,
        desde=asignacion.desde,
        vence_en=asignacion.vence_en,
        revocada_en=asignacion.revocada_en,
        otorgada_por=asignacion.otorgada_por,
        vigente=_es_vigente(asignacion, ahora),
    )


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
        uow: UsuariosUnitOfWork,
    ) -> tuple[Usuario, str, list[str]]:
        """Inicia sesión con rate-limit (RN-08) y timing defense (RN-09).

        La lectura de usuario y roles se realiza a través del Unit of Work.
        DD-04: Sólo el intento de acceso se audita en una sesión independiente.
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

        # 3. Búsqueda de usuario y verificación timing-safe (RN-09) vía UoW
        async with uow:
            usuario = await uow.usuarios.get_by_email(email)

            if usuario is not None and usuario.activo:
                target_hash = usuario.password_hash
            else:
                target_hash = dummy_hash

            pwd_valida = await verify_password(password, target_hash)
            exito = bool(pwd_valida and usuario is not None and usuario.activo)

            if exito:
                roles = await uow.roles.get_roles_vigentes(usuario.id)
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

    @staticmethod
    async def cambiar_password(
        usuario_id: int,
        dto: CambiarPasswordRequest,
        roles: list[str],
        session_factory: async_sessionmaker[AsyncSession],
        uow: UsuariosUnitOfWork,
    ) -> tuple[Usuario, str]:
        """Cambia la contraseña autenticada e invalida sesiones previas (RN-07).

        La lectura y la verificación bcrypt ocurren fuera de la transacción;
        la escritura y la auditoría se confirman atómicamente en el UoW.
        """
        async with session_factory() as session_lectura:
            repo = UsuarioRepository(session_lectura)
            usuario_actual = await repo.get_by_id(usuario_id)
            if usuario_actual is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no encontrado",
                )
            password_hash_actual = usuario_actual.password_hash

        if not await verify_password(dto.password_actual, password_hash_actual):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="La contraseña actual es incorrecta",
            )

        nuevo_hash = await hash_password(dto.password_nueva)
        momento = datetime.now(timezone.utc)

        async with uow:
            usuario = await uow.usuarios.get_by_id(usuario_id)
            if usuario is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no encontrado",
                )
            usuario.password_hash = nuevo_hash
            usuario.debe_cambiar_password = False
            usuario.password_cambiada_en = momento
            await uow.usuarios.update(usuario)
            await uow.eventos.add(
                EventoSeguridad(actor=usuario.email, accion=ACCION_CAMBIO_PASSWORD)
            )

        token = crear_access_token(
            {
                "sub": usuario.email,
                "user_id": usuario.id,
                "roles": roles,
            },
            emitido_en=momento,
        )
        return usuario, token


class PersonalService:
    """Gestión de personal y asignaciones de rol (sólo ADMIN)."""

    @staticmethod
    async def crear_usuario(
        dto: CrearUsuarioRequest,
        actor: UsuarioActual,
        uow: UsuariosUnitOfWork,
    ) -> tuple[Usuario, list[str]]:
        """Da de alta personal con contraseña provisoria y su rol vigente."""
        pwd_hash = await hash_password(dto.password)

        async with uow:
            usuario = Usuario(
                email=dto.email,
                nombre=dto.nombre,
                password_hash=pwd_hash,
                activo=True,
                debe_cambiar_password=True,
            )
            usuario = await uow.usuarios.add(usuario)
            await uow.roles.add(
                AsignacionRol(
                    usuario_id=usuario.id,
                    rol=dto.rol,
                    otorgada_por=actor.id,
                )
            )
            await uow.eventos.add(
                EventoSeguridad(actor=actor.email, accion=ACCION_ALTA_USUARIO)
            )

        return usuario, [dto.rol]

    @staticmethod
    async def asignar_rol(
        usuario_id: int,
        dto: AsignarRolRequest,
        actor: UsuarioActual,
        uow: UsuariosUnitOfWork,
    ) -> AsignacionRol:
        """Asigna un rol; si existe una asignación abierta vencida, la reemplaza."""
        async with uow:
            usuario = await uow.usuarios.get_by_id(usuario_id)
            if usuario is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Usuario no encontrado",
                )

            ahora = datetime.now(timezone.utc)
            existente = await uow.roles.get_abierta(usuario_id, dto.rol, for_update=True)

            if existente is not None:
                if _es_vigente(existente, ahora):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="El usuario ya posee ese rol vigente",
                    )
                existente.revocada_en = ahora
                await uow.roles.update(existente)

            asignacion = AsignacionRol(
                usuario_id=usuario_id,
                rol=dto.rol,
                desde=ahora,
                vence_en=dto.vence_en,
                otorgada_por=actor.id,
            )
            asignacion = await uow.roles.add(asignacion)
            await uow.eventos.add(
                EventoSeguridad(actor=actor.email, accion=ACCION_ASIGNACION_ROL)
            )

        return asignacion

    @staticmethod
    async def revocar_rol(
        usuario_id: int,
        rol: str,
        actor: UsuarioActual,
        uow: UsuariosUnitOfWork,
    ) -> AsignacionRol:
        """Revoca una asignación abierta respetando la autoprotección admin (RN-05)."""
        async with uow:
            usuario = await uow.usuarios.get_by_id(usuario_id)
            if usuario is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Usuario no encontrado",
                )

            asignacion = await uow.roles.get_abierta(usuario_id, rol, for_update=True)
            if asignacion is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Asignación de rol no encontrada",
                )

            if rol == "ADMIN" and usuario_id == actor.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Un administrador no puede revocar su propio rol ADMIN",
                )

            if rol == "ADMIN":
                restantes = await uow.roles.contar_admins_vigentes(
                    excluir_id=asignacion.id
                )
                if restantes == 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="El sistema no puede quedar sin administradores vigentes",
                    )

            asignacion.revocada_en = datetime.now(timezone.utc)
            await uow.roles.update(asignacion)
            await uow.eventos.add(
                EventoSeguridad(actor=actor.email, accion=ACCION_REVOCACION_ROL)
            )

        return asignacion

    @staticmethod
    async def listar_roles(
        usuario_id: int,
        uow: UsuariosUnitOfWork,
    ) -> list[AsignacionRolResponse]:
        """Devuelve el historial completo de asignaciones con indicador de vigencia."""
        async with uow:
            usuario = await uow.usuarios.get_by_id(usuario_id)
            if usuario is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Usuario no encontrado",
                )
            asignaciones = await uow.roles.listar_por_usuario(usuario_id)

        ahora = datetime.now(timezone.utc)
        return [armar_asignacion_response(a, ahora) for a in asignaciones]


class AuditoriaService:
    """Consulta paginada de eventos de seguridad."""

    @staticmethod
    async def listar_eventos(
        page: int,
        size: int,
        uow: UsuariosUnitOfWork,
    ) -> PaginatedResponse[EventoSeguridadResponse]:
        async with uow:
            total = await uow.eventos.count()
            eventos = await uow.eventos.listar_paginado(
                offset=(page - 1) * size,
                limit=size,
            )

        items = [
            EventoSeguridadResponse(
                id=evento.id,
                cuando=evento.cuando,
                actor=evento.actor,
                accion=evento.accion,
            )
            for evento in eventos
        ]
        return armar_paginacion(items, total, page, size)
