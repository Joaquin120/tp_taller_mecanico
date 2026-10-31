import math
from collections.abc import Sequence
from typing import Generic, TypeVar
from fastapi import HTTPException, Query, status
from pydantic import Field

from app.core.schemas import BaseSchema

T = TypeVar("T")


class ParamsPaginacion(BaseSchema):
    """Parámetros query estándar de paginación."""

    page: int = Field(default=1, ge=1, description="Número de página (1-based)")
    size: int = Field(default=20, ge=1, le=100, description="Tamaño de página (máximo 100)")


class PaginatedResponse(BaseSchema, Generic[T]):
    """Envoltorio estandarizado de respuesta paginada."""

    items: list[T] = Field(description="Listado de elementos de la página actual")
    total: int = Field(ge=0, description="Total general de elementos")
    page: int = Field(ge=1, description="Página solicitada")
    size: int = Field(ge=1, le=100, description="Elementos por página")
    pages: int = Field(ge=1, description="Total de páginas calculadas")


def armar_paginacion(
    items: Sequence[T],
    total: int,
    page: int,
    size: int,
) -> PaginatedResponse[T]:
    """Valida los límites y construye el DTO de respuesta paginada.

    Lanza HTTP 422 si la página solicitada excede la última página calculable.
    """
    if size <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El tamaño de página debe ser mayor a 0",
        )

    pages = max(1, math.ceil(total / size)) if total > 0 else 1

    if page > pages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Página fuera de rango. Página solicitada: {page}, total de páginas: {pages}",
        )

    return PaginatedResponse[T](
        items=list(items),
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
