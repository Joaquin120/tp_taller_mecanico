from pydantic import BaseModel, ConfigDict, Field


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


class LoginRequest(BaseDTO):
    """Payload para inicio de sesión."""

    email: str
    password: str = Field(max_length=72)


class UsuarioResponse(BaseDTO):
    """Respuesta básica de usuario. Jamás expone password_hash."""

    id: int
    email: str
    nombre: str
    activo: bool
    debe_cambiar_password: bool


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
