from collections.abc import AsyncGenerator
from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def crear_motor(
    database_url: str,
    pool_size: int = 10,
    echo: bool = False,
) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        echo=echo,
        future=True,
    )


def crear_fabrica_sesiones(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session
