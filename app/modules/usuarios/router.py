from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UsuarioActual, get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.modules.usuarios.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RegistroClienteRequest,
    RegistroClienteResponse,
    YoResponse,
)
from app.modules.usuarios.service import AuthService
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork

router = APIRouter(prefix="", tags=["auth"])


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
