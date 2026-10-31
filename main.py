from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import bcrypt
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import crear_fabrica_sesiones, crear_motor
from app.modules.health.router import router as health_router
from app.modules.usuarios.router import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    app.state.engine = crear_motor(
        database_url=settings.database_url,
        pool_size=settings.DATABASE_POOL_SIZE,
        echo=settings.SQL_ECHO,
    )
    app.state.session_factory = crear_fabrica_sesiones(app.state.engine)

    dummy_salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    app.state.dummy_hash = bcrypt.hashpw(
        b"timing_defense_dummy_pass",
        dummy_salt,
    ).decode("utf-8")

    yield

    await app.state.engine.dispose()


app = FastAPI(
    title="Taller Mecánico API",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(auth_router, prefix="/auth")
