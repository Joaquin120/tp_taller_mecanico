from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.core.schemas import BaseSchema


class ItemOrdenRequest(BaseSchema):
    """Ítem solicitado al crear una orden; el precio no viaja (RN-10)."""

    repuesto_id: int
    cantidad: int = Field(gt=0)


class OrdenCrearRequest(BaseSchema):
    """Payload de alta de orden de trabajo (RN-10)."""

    vehiculo_id: int
    falla: str = Field(min_length=1, max_length=500)
    items: list[ItemOrdenRequest] = Field(min_length=1)


class ItemOrdenResponse(BaseSchema):
    """Ítem de una orden con el precio copiado del repuesto."""

    repuesto_id: int
    codigo: str
    descripcion: str
    cantidad: int
    precio_unitario: Decimal
    subtotal: Decimal


class HistorialEstadoResponse(BaseSchema):
    """Línea del historial de estados (sólo agregado)."""

    desde_estado: str | None = None
    hasta_estado: str
    usuario_id: int
    cuando: datetime


class OrdenResponse(BaseSchema):
    """Detalle de una orden de trabajo."""

    id: int
    estado: str
    patente: str
    creada_en: datetime
    total: Decimal
    mecanico_id: int | None = None
    falla: str
    cliente: str
    items: list[ItemOrdenResponse]
    historial: list[HistorialEstadoResponse]


class OrdenResumenResponse(BaseSchema):
    """Resumen de una orden para listados."""

    id: int
    estado: str
    vehiculo_id: int
    patente: str
    mecanico_id: int | None = None
    falla: str
    creada_en: datetime
    total: Decimal


class EstadoOrdenResponse(BaseSchema):
    """Fila del catálogo de estados."""

    codigo: str
    descripcion: str
    posicion: int
    es_final: bool
