"""Contratos Pydantic del módulo de órdenes de trabajo.

Reglas duras:
- `extra="forbid"` heredado de `BaseSchema`: el cliente nunca envía precio,
  subtotal, total, estado ni mecánico (RN-10).
- El dinero se valida y se transporta como `Decimal`; nunca `float`.
- Las fechas se transportan con zona horaria.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from app.core.schemas import BaseSchema

FallaOrden = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


class ItemOrdenRequest(BaseSchema):
    """Ítem solicitado al crear una orden; sólo repuesto y cantidad (RN-10)."""

    repuesto_id: int = Field(gt=0)
    cantidad: int = Field(gt=0)


class OrdenCrearRequest(BaseSchema):
    """Payload de alta de orden: el precio y el total los calcula el servidor."""

    vehiculo_id: int = Field(gt=0)
    falla: FallaOrden
    items: list[ItemOrdenRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def _sin_repuestos_repetidos(self) -> "OrdenCrearRequest":
        ids = [item.repuesto_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("No se puede repetir un repuesto en la misma orden")
        return self


class EstadoOrdenResponse(BaseSchema):
    """Fila del catálogo de estados de orden."""

    codigo: str
    descripcion: str
    posicion: int
    es_final: bool


class ItemOrdenResponse(BaseSchema):
    """Ítem de una orden con el precio copiado del repuesto."""

    repuesto_id: int
    codigo: str
    descripcion: str
    cantidad: int
    precio_unitario: Decimal
    subtotal: Decimal


class HistorialEstadoResponse(BaseSchema):
    """Línea del historial de estados (tabla de sólo agregado)."""

    desde_estado: str | None = None
    hasta_estado: str
    usuario_id: int
    cuando: datetime


class OrdenResponse(BaseSchema):
    """Detalle completo de una orden de trabajo."""

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
    """Resumen de una orden para listados paginados."""

    id: int
    estado: str
    vehiculo_id: int
    patente: str
    mecanico_id: int | None = None
    falla: str
    creada_en: datetime
    total: Decimal
