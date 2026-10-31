from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UsuarioActual, get_current_user, requiere_rol
from app.core.config import get_settings
from app.core.database import get_session
from app.core.paginacion import PaginatedResponse, ParamsPaginacion
from app.modules.usuarios.schemas import (
    AsignacionRolResponse,
    AsignarRolRequest,
    CambiarPasswordRequest,
    CambiarPasswordResponse,
    CrearUsuarioRequest,
    EventoSeguridadResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MensajeResponse,
    RegistroClienteRequest,
    RegistroClienteResponse,
    UsuarioCreadoResponse,
    YoResponse,
)
from app.modules.usuarios.service import AuditoriaService, AuthService, PersonalService, armar_asignacion_response
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork

router = APIRouter(prefix="", tags=["auth"])
router_protegido = APIRouter(prefix="", tags=["protegido"])


async def get_usuarios_uow(
    session: AsyncSession = Depends(get_session),
) -> UsuariosUnitOfWork:
    return UsuariosUnitOfWork(session)


@router.post(
    "/registro",
    response_model=RegistroClienteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Auto-registro atómico de cliente",
)
async def registrar_cliente(
    payload: RegistroClienteRequest,
    uow: UsuariosUnitOfWork = Depends(get_usuarios_uow),
) -> RegistroClienteResponse:
    """Registra atómicamente Usuario + Rol CLIENTE + Cliente en una sola transacción (RN-02)."""
    usuario, roles, cliente_id = await AuthService.registrar_cliente(payload, uow)
    return RegistroClienteResponse(
        id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        roles=roles,
        cliente_id=cliente_id,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Inicio de sesión con cookie HttpOnly y rate limit",
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    """Inicia sesión, verifica rate-limit (RN-08) y emite token en cookie HttpOnly (DD-02).

    El cuerpo de respuesta jamás contiene el JWT.
    """
    settings = get_settings()

    # Obtener IP del cliente (priorizando X-Forwarded-For si está detrás de proxy)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "127.0.0.1"

    session_factory = request.app.state.session_factory

    usuario, token, roles = await AuthService.login(
        email=payload.email,
        password=payload.password,
        ip=client_ip,
        app_state_or_dummy_hash=request.app.state,
        session_factory=session_factory,
    )

    # Establecer cookie segura HttpOnly
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.JWT_EXPIRATION_SECONDS,
        secure=settings.COOKIE_SECURE,
    )

    return LoginResponse(
        mensaje="Inicio de sesión exitoso",
        email=usuario.email,
        roles=roles,
    )


@router.post(
    "/cambiar-password",
    response_model=CambiarPasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Cambio de contraseña autenticado",
)
async def cambiar_password(
    payload: CambiarPasswordRequest,
    request: Request,
    response: Response,
    usuario: UsuarioActual = Depends(get_current_user),
    uow: UsuariosUnitOfWork = Depends(get_usuarios_uow),
) -> CambiarPasswordResponse:
    """Cambia la contraseña, desbloquea el grupo protegido e invalida sesiones previas (RN-07)."""
    settings = get_settings()
    _, token = await AuthService.cambiar_password(
        usuario_id=usuario.id,
        dto=payload,
        roles=usuario.roles,
        session_factory=request.app.state.session_factory,
        uow=uow,
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.JWT_EXPIRATION_SECONDS,
        secure=settings.COOKIE_SECURE,
    )

    return CambiarPasswordResponse(
        mensaje="Contraseña actualizada correctamente",
        debe_cambiar_password=False,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Cierre de sesión",
)
async def logout(response: Response) -> LogoutResponse:
    """Elimina la cookie de sesión estableciendo Max-Age=0."""
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax",
    )
    return LogoutResponse(mensaje="Sesión cerrada correctamente")


@router.get(
    "/yo",
    response_model=YoResponse,
    status_code=status.HTTP_200_OK,
    summary="Información de la sesión actual",
)
async def obtener_yo(
    usuario: UsuarioActual = Depends(get_current_user),
) -> YoResponse:
    """Retorna los datos del usuario autenticado con roles vigentes de base de datos."""
    return YoResponse(
        id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        roles=usuario.roles,
        roles_token=usuario.roles_token,
        debe_cambiar_password=usuario.debe_cambiar_password,
        cliente_id=usuario.cliente_id,
    )

@router_protegido.post(
    "/usuarios",
    response_model=UsuarioCreadoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de personal con contraseña provisoria",
)
async def crear_usuario(
    payload: CrearUsuarioRequest,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: UsuariosUnitOfWork = Depends(get_usuarios_uow),
) -> UsuarioCreadoResponse:
    """Crea un usuario de personal con rol vigente y cambio de contraseña pendiente."""
    usuario, roles = await PersonalService.crear_usuario(payload, actor, uow)
    return UsuarioCreadoResponse(
        id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        activo=usuario.activo,
        debe_cambiar_password=usuario.debe_cambiar_password,
        roles=roles,
    )


@router_protegido.get(
    "/usuarios/{id}/roles",
    response_model=list[AsignacionRolResponse],
    status_code=status.HTTP_200_OK,
    summary="Historial de roles de un usuario",
)
async def listar_roles(
    id: int,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: UsuariosUnitOfWork = Depends(get_usuarios_uow),
) -> list[AsignacionRolResponse]:
    """Devuelve todas las asignaciones del usuario, vigentes e históricas."""
    return await PersonalService.listar_roles(id, uow)


@router_protegido.post(
    "/usuarios/{id}/roles",
    response_model=AsignacionRolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asignación de rol",
)
async def asignar_rol(
    id: int,
    payload: AsignarRolRequest,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: UsuariosUnitOfWork = Depends(get_usuarios_uow),
) -> AsignacionRolResponse:
    """Asigna un rol vigente o reemplaza una asignación abierta vencida."""
    asignacion = await PersonalService.asignar_rol(id, payload, actor, uow)
    return armar_asignacion_response(asignacion)


@router_protegido.delete(
    "/usuarios/{id}/roles/{rol}",
    response_model=MensajeResponse,
    status_code=status.HTTP_200_OK,
    summary="Revocación de rol",
)
async def revocar_rol(
    id: int,
    rol: str,
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: UsuariosUnitOfWork = Depends(get_usuarios_uow),
) -> MensajeResponse:
    """Revoca una asignación abierta respetando la autoprotección admin (RN-05)."""
    await PersonalService.revocar_rol(id, rol, actor, uow)
    return MensajeResponse(mensaje="Rol revocado correctamente", rol=rol)


@router_protegido.get(
    "/eventos",
    response_model=PaginatedResponse[EventoSeguridadResponse],
    status_code=status.HTTP_200_OK,
    summary="Consulta paginada de eventos de seguridad",
)
async def listar_eventos(
    params: ParamsPaginacion = Depends(),
    actor: UsuarioActual = Depends(requiere_rol("ADMIN")),
    uow: UsuariosUnitOfWork = Depends(get_usuarios_uow),
) -> PaginatedResponse[EventoSeguridadResponse]:
    """Lista los eventos de seguridad del más reciente al más antiguo."""
    return await AuditoriaService.listar_eventos(params.page, params.size, uow)
