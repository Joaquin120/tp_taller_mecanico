from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RolPersonal = Literal["ADMIN", "RECEPCION", "MECANICO"]
RolCatalogo = Literal["ADMIN", "RECEPCION", "MECANICO", "CLIENTE"]


def _validar_72_bytes(valor: str) -> str:
    """Rechaza contraseñas que superan el límite real de bcrypt (72 bytes UTF-8)."""

    if len(valor.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar los 72 bytes UTF-8")
    return valor


class BaseDTO(BaseModel):
    """Contrato base Pydantic que prohíbe atributos adicionales no declarados."""

    model_config = ConfigDict(extra="forbid")


class RegistroClienteRequest(BaseDTO):
    """Payload para el auto-registro de un nuevo cliente (RN-02)."""

    email: str
    password: str = Field(min_length=6, max_length=72)
    nombre: str = Field(min_length=1, max_length=255)
    documento: str = Field(min_length=1, max_length=50)
    telefono: str = Field(min_length=1, max_length=50)

    @field_validator("password")
    @classmethod
    def _password_bytes(cls, valor: str) -> str:
        return _validar_72_bytes(valor)


class LoginRequest(BaseDTO):
    """Payload para inicio de sesión."""

    email: str
    password: str = Field(max_length=72)

    @field_validator("password")
    @classmethod
    def _password_bytes(cls, valor: str) -> str:
        return _validar_72_bytes(valor)


class CambiarPasswordRequest(BaseDTO):
    """Payload para el cambio de contraseña autenticado."""

    password_actual: str = Field(min_length=6, max_length=72)
    password_nueva: str = Field(min_length=6, max_length=72)

    @field_validator("password_actual", "password_nueva")
    @classmethod
    def _password_bytes(cls, valor: str) -> str:
        return _validar_72_bytes(valor)


class CrearUsuarioRequest(BaseDTO):
    """Payload para el alta de personal con contraseña provisoria."""

    email: str = Field(min_length=3, max_length=255)
    nombre: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=6, max_length=72)
    rol: RolPersonal

    @field_validator("password")
    @classmethod
    def _password_bytes(cls, valor: str) -> str:
        return _validar_72_bytes(valor)


class AsignarRolRequest(BaseDTO):
    """Payload para asignar un rol con vencimiento opcional."""

    rol: RolCatalogo
    vence_en: datetime | None = None

    @field_validator("vence_en")
    @classmethod
    def _vence_en_valido(cls, valor: datetime | None) -> datetime | None:
        if valor is None:
            return valor
        if valor.tzinfo is None or valor.utcoffset() is None:
            raise ValueError("vence_en debe incluir zona horaria")
        if valor <= datetime.now(timezone.utc):
            raise ValueError("vence_en debe ser una fecha futura")
        return valor


class UsuarioResponse(BaseDTO):
    """Respuesta básica de usuario. Jamás expone password_hash."""

    id: int
    email: str
    nombre: str
    activo: bool
    debe_cambiar_password: bool


class UsuarioCreadoResponse(UsuarioResponse):
    """Respuesta del alta de personal."""

    roles: list[str]


class AsignacionRolResponse(BaseDTO):
    """Respuesta de una asignación de rol, vigente o histórica."""

    id: int
    usuario_id: int
    rol: str
    desde: datetime
    vence_en: datetime | None = None
    revocada_en: datetime | None = None
    otorgada_por: int | None = None
    vigente: bool


class EventoSeguridadResponse(BaseDTO):
    """Respuesta de un evento de seguridad."""

    id: int
    cuando: datetime
    actor: str
    accion: str


class RegistroClienteResponse(BaseDTO):
    """Respuesta exitosa al auto-registro."""

    id: int
    email: str
    nombre: str
    roles: list[str]
    cliente_id: int | None = None


class LoginResponse(BaseDTO):
    """Respuesta exitosa de login. El JWT viaja exclusivamente en Set-Cookie."""

    mensaje: str = "Inicio de sesión exitoso"
    email: str
    roles: list[str]


class CambiarPasswordResponse(BaseDTO):
    """Respuesta exitosa del cambio de contraseña."""

    mensaje: str = "Contraseña actualizada correctamente"
    debe_cambiar_password: bool = False


class YoResponse(BaseDTO):
    """Información del usuario autenticado actual."""

    id: int
    email: str
    nombre: str
    roles: list[str]
    roles_token: list[str]
    debe_cambiar_password: bool
    cliente_id: int | None = None


class LogoutResponse(BaseDTO):
    """Respuesta al cierre de sesión."""

    mensaje: str = "Sesión cerrada correctamente"


class MensajeResponse(BaseDTO):
    """Respuesta genérica con mensaje de negocio."""

    mensaje: str
    rol: str | None = None
