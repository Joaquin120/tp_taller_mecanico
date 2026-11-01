import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
import bcrypt
import jwt

from app.core.config import get_settings

_bcrypt_semaphores: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


def get_bcrypt_semaphore() -> asyncio.Semaphore:
    """Retorna el semáforo concurrente para limitar operaciones de bcrypt en CPU."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        if loop not in _bcrypt_semaphores:
            settings = get_settings()
            _bcrypt_semaphores[loop] = asyncio.Semaphore(settings.MAX_CONCURRENT_BCRYPT)
        return _bcrypt_semaphores[loop]
    settings = get_settings()
    return asyncio.Semaphore(settings.MAX_CONCURRENT_BCRYPT)


async def hash_password(plain: str) -> str:
    """Hashea una contraseña con bcrypt fuera del event loop bajo un semáforo.

    Regla dura (DD-03):
    - Trunca la entrada estrictamente a 72 bytes.
    - Se ejecuta en asyncio.to_thread acotado por MAX_CONCURRENT_BCRYPT.
    """
    settings = get_settings()
    semaphore = get_bcrypt_semaphore()
    plain_bytes = plain.encode("utf-8")[:72]

    def _hash() -> str:
        salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
        return bcrypt.hashpw(plain_bytes, salt).decode("utf-8")

    async with semaphore:
        return await asyncio.to_thread(_hash)


async def verify_password(plain: str, hashed: str) -> bool:
    """Verifica una contraseña contra un hash con bcrypt fuera del event loop.

    Regla dura (DD-03):
    - Trunca la entrada estrictamente a 72 bytes.
    - Se ejecuta en asyncio.to_thread acotado por MAX_CONCURRENT_BCRYPT.
    """
    semaphore = get_bcrypt_semaphore()
    plain_bytes = plain.encode("utf-8")[:72]
    hashed_bytes = hashed.encode("utf-8")

    def _verify() -> bool:
        try:
            return bcrypt.checkpw(plain_bytes, hashed_bytes)
        except Exception:
            return False

    async with semaphore:
        return await asyncio.to_thread(_verify)


def crear_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
    emitido_en: datetime | None = None,
) -> str:
    """Genera un token JWT firmado según la configuración del sistema.

    Incluye sub, iat (con precisión) y exp. ``emitido_en`` permite fijar la
    base de emisión para que el token del cambio de contraseña use exactamente
    el mismo timestamp que ``password_cambiada_en`` (RN-07).
    """
    settings = get_settings()
    to_encode = data.copy()
    now = emitido_en or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(seconds=settings.JWT_EXPIRATION_SECONDS)

    to_encode.update(
        {
            "iat": now.timestamp(),
            "exp": expire.timestamp(),
        }
    )
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decodificar_access_token(token: str) -> dict[str, Any]:
    """Decodifica y valida la firma y expiración de un token JWT."""
    settings = get_settings()
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
