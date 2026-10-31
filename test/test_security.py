import asyncio
from datetime import timedelta
import pytest
import jwt

from app.core.security import (
    crear_access_token,
    decodificar_access_token,
    hash_password,
    verify_password,
)


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_jwt_secret_key_1234567890")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")  # rounds bajos para tests veloces


@pytest.mark.asyncio
async def test_hash_password_returns_verifiable_hash():
    password = "SuperPassword123"
    hashed = await hash_password(password)

    assert hashed is not None
    assert isinstance(hashed, str)
    assert hashed != password
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    assert await verify_password(password, hashed) is True


@pytest.mark.asyncio
async def test_verify_password_correct():
    password = "mi_clave_secreta"
    hashed = await hash_password(password)

    resultado = await verify_password(password, hashed)
    assert resultado is True


@pytest.mark.asyncio
async def test_verify_password_incorrect():
    password = "mi_clave_secreta"
    hashed = await hash_password(password)

    resultado = await verify_password("otra_clave_erronea", hashed)
    assert resultado is False


@pytest.mark.asyncio
async def test_password_over_72_bytes_truncated():
    # Longitud de 72 bytes + sufijo diferente
    base = "A" * 72
    password_1 = base + "XYZ_EXTRA"
    password_2 = base + "123_DIFERENTE"

    hashed_1 = await hash_password(password_1)

    # password_2 debe coincidir con hashed_1 porque los primeros 72 bytes son idénticos
    assert await verify_password(password_2, hashed_1) is True


@pytest.mark.asyncio
async def test_empty_password_hashable():
    empty_pwd = ""
    hashed = await hash_password(empty_pwd)

    assert await verify_password("", hashed) is True
    assert await verify_password("no_vacia", hashed) is False


@pytest.mark.asyncio
async def test_semaphore_concurrent_calls():
    # Ejecuta múltiples hashes concurrentemente para comprobar que el semáforo no bloquea ni crashea
    passwords = [f"password_{i}" for i in range(8)]
    hashes = await asyncio.gather(*(hash_password(p) for p in passwords))

    assert len(hashes) == 8
    verificaciones = await asyncio.gather(
        *(verify_password(p, h) for p, h in zip(passwords, hashes))
    )
    assert all(verificaciones)


def test_crear_y_decodificar_access_token():
    payload = {"sub": "juan@example.com", "roles": ["ADMIN", "MECANICO"]}
    token = crear_access_token(payload)

    assert isinstance(token, str)
    decoded = decodificar_access_token(token)

    assert decoded["sub"] == "juan@example.com"
    assert decoded["roles"] == ["ADMIN", "MECANICO"]
    assert "iat" in decoded
    assert "exp" in decoded


def test_token_expirado_falla():
    payload = {"sub": "expirado@example.com"}
    token = crear_access_token(payload, expires_delta=timedelta(seconds=-10))

    with pytest.raises(jwt.ExpiredSignatureError):
        decodificar_access_token(token)


def test_token_invalido_falla():
    with pytest.raises(jwt.PyJWTError):
        decodificar_access_token("token_invalido_malformado")
