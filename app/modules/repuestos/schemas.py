"""Contratos Pydantic del módulo de repuestos.

Reglas duras:
- `extra="forbid"` heredado de `BaseSchema`: `stock` no puede viajar en el PATCH (RN-14).
- El precio se valida como `Decimal` con 2 decimales y mayor a cero.
- Los textos se normalizan con `strip` y rechazan cadenas vacías.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from app.core.schemas import BaseSchema

CodigoRepuesto = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]
DescripcionRepuesto = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
PrecioPositivo = Annotated[
    Decimal,
    Field(gt=0, max_digits=10, decimal_places=2),
]


class RepuestoCreate(BaseSchema):
    """Alta de repuesto con stock inicial opcional."""

    codigo: CodigoRepuesto
    descripcion: DescripcionRepuesto
    precio: PrecioPositivo
    stock_inicial: int = Field(default=0, ge=0)


class RepuestoUpdate(BaseSchema):
    """Modificación de descripción y/o precio; el stock queda explícitamente afuera."""

    descripcion: DescripcionRepuesto | None = None
    precio: PrecioPositivo | None = None

    @model_validator(mode="after")
    def _exigir_al_menos_un_campo(self) -> "RepuestoUpdate":
        if self.descripcion is None and self.precio is None:
            raise ValueError("Debe enviar al menos descripcion o precio")
        return self


class ReponerStockRequest(BaseSchema):
    """Reposición de stock con cantidad estrictamente positiva."""

    cantidad: int = Field(gt=0)


class RepuestoResponse(BaseSchema):
    """Representación pública de un repuesto vigente."""

    id: int
    codigo: str
    descripcion: str
    precio: Decimal
    stock: int


class MovimientoStockResponse(BaseSchema):
    """Fila del historial de movimientos de stock."""

    id: int
    cantidad: int
    motivo: str
    cuando: datetime
    usuario_id: int
    orden_id: int | None = None


class HistorialPrecioResponse(BaseSchema):
    """Fila del historial de cambios de precio."""

    id: int
    precio_anterior: Decimal
    precio_nuevo: Decimal
    cuando: datetime
    usuario_id: int
