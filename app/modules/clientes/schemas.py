from datetime import datetime
from pydantic import ConfigDict, Field, field_validator

from app.core.schemas import BaseSchema


class ClienteCreateRequest(BaseSchema):
    """Payload para la creación de un nuevo cliente."""

    nombre: str = Field(min_length=1, max_length=255)
    documento: str = Field(min_length=1, max_length=50)
    telefono: str = Field(min_length=1, max_length=50)


class VehiculoResponse(BaseSchema):
    """Representación pública de un vehículo."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    cliente_id: int
    patente: str
    marca: str
    modelo: str
    anio: int
    borrado_en: datetime | None = None


class ClienteResponse(BaseSchema):
    """Representación pública básica de un cliente."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    nombre: str
    documento: str
    telefono: str
    usuario_id: int | None = None


class ClienteDetalleResponse(ClienteResponse):
    """Representación pública de un cliente con su flota de vehículos vigentes."""

    vehiculos: list[VehiculoResponse] = Field(default_factory=list)


class VehiculoCreateRequest(BaseSchema):
    """Payload para el registro de un vehículo."""

    patente: str = Field(min_length=1, max_length=20)
    marca: str = Field(min_length=1, max_length=100)
    modelo: str = Field(min_length=1, max_length=100)
    anio: int = Field(ge=1950, le=2100)

    @field_validator("patente")
    @classmethod
    def normalizar_patente(cls, v: str) -> str:
        patente = v.strip().upper()
        if not patente:
            raise ValueError("La patente no puede estar vacía")
        return patente
