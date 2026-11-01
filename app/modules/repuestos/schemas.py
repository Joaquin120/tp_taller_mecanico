from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.core.schemas import BaseSchema


class RepuestoCrearRequest(BaseSchema):
    """Payload de alta de repuesto con stock inicial (RN-14)."""

    codigo: str = Field(min_length=1, max_length=50)
    descripcion: str = Field(min_length=1, max_length=255)
    precio: Decimal = Field(gt=0)
    stock_inicial: int = Field(default=0, ge=0)


class RepuestoActualizarRequest(BaseSchema):
    """PATCH parcial: sólo descripción y precio; el stock no se edita (RN-14)."""

    descripcion: str | None = Field(default=None, min_length=1, max_length=255)
    precio: Decimal | None = Field(default=None, gt=0)


class ReponerStockRequest(BaseSchema):
    """Payload de reposición de stock."""

    cantidad: int = Field(gt=0)


class RepuestoResponse(BaseSchema):
    """Respuesta de un repuesto."""

    id: int
    codigo: str
    descripcion: str
    precio: Decimal
    stock: int


class MovimientoStockResponse(BaseSchema):
    """Respuesta de un movimiento de stock (sólo agregado)."""

    id: int
    repuesto_id: int
    orden_id: int | None = None
    usuario_id: int
    cantidad: int
    motivo: str
    cuando: datetime


class HistorialPrecioResponse(BaseSchema):
    """Respuesta de una línea del historial de precios (sólo agregado)."""

    id: int
    repuesto_id: int
    usuario_id: int
    precio_anterior: Decimal
    precio_nuevo: Decimal
    cuando: datetime
