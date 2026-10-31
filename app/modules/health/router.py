from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session

router = APIRouter(prefix="/health", tags=["Salud"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def health_live() -> dict[str, Any]:
    return {"status": "ok", "alive": True}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def health_ready(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible",
        ) from exc
