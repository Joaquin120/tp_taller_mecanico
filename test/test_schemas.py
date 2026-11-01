from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from app.core.schemas import BaseSchema
from app.modules.usuarios.schemas import (
    AsignarRolRequest,
    CambiarPasswordRequest,
    CrearUsuarioRequest,
    LoginRequest,
    RegistroClienteRequest,
)


class DummySchema(BaseSchema):
    nombre: str
    edad: int


class NestedSchema(BaseSchema):
    detalle: DummySchema


def test_base_schema_rejects_extra_fields():
    with pytest.raises(ValidationError) as exc_info:
        DummySchema(nombre="Juan", edad=30, campo_extra="no_permitido")

    errors = exc_info.value.errors()
    assert any(
        err["loc"] == ("campo_extra",) and err["type"] == "extra_forbidden"
        for err in errors
    )


def test_base_schema_accepts_valid_fields():
    obj = DummySchema(nombre="Juan", edad=30)
    assert obj.nombre == "Juan"
    assert obj.edad == 30


def test_base_schema_nested_rejects_extra_fields():
    with pytest.raises(ValidationError) as exc_info:
        NestedSchema(detalle={"nombre": "Ana", "edad": 25, "extra": "invalido"})

    errors = exc_info.value.errors()
    assert any(
        "extra" in str(err["loc"]) and err["type"] == "extra_forbidden"
        for err in errors
    )


def test_crear_usuario_request_valid():
    req = CrearUsuarioRequest(
        email="mecanico@test.com",
        nombre="Carlos Mecanico",
        password="PasswordValido123",
        rol="MECANICO",
    )
    assert req.email == "mecanico@test.com"
    assert req.rol == "MECANICO"


def test_crear_usuario_request_rechaza_rol_no_personal():
    with pytest.raises(ValidationError) as exc_info:
        CrearUsuarioRequest(
            email="cliente@test.com",
            nombre="Laura",
            password="Password123",
            rol="CLIENTE",
        )
    assert any(err["loc"] == ("rol",) for err in exc_info.value.errors())


def test_crear_usuario_request_rechaza_password_corta():
    with pytest.raises(ValidationError):
        CrearUsuarioRequest(
            email="user@test.com",
            nombre="User",
            password="123",
            rol="ADMIN",
        )


def test_contrasenas_rechazan_mas_de_72_bytes_utf8_multibyte():
    # 'ñ' ocupa 2 bytes en UTF-8. 40 * 2 = 80 bytes > 72 bytes
    password_multibyte_larga = "ñ" * 40
    assert len(password_multibyte_larga) == 40  # 40 caracteres
    assert len(password_multibyte_larga.encode("utf-8")) == 80  # 80 bytes

    with pytest.raises(ValidationError):
        CrearUsuarioRequest(
            email="admin@test.com",
            nombre="Admin",
            password=password_multibyte_larga,
            rol="ADMIN",
        )

    with pytest.raises(ValidationError):
        LoginRequest(
            email="admin@test.com",
            password=password_multibyte_larga,
        )

    with pytest.raises(ValidationError):
        RegistroClienteRequest(
            email="nuevo@test.com",
            nombre="Nuevo",
            password=password_multibyte_larga,
            documento="12345678",
            telefono="11223344",
        )

    with pytest.raises(ValidationError):
        CambiarPasswordRequest(
            password_actual="valida123",
            password_nueva=password_multibyte_larga,
        )


def test_contrasena_exactamente_72_bytes_aceptada():
    password_72_bytes = "a" * 72
    req = CrearUsuarioRequest(
        email="admin@test.com",
        nombre="Admin",
        password=password_72_bytes,
        rol="ADMIN",
    )
    assert req.password == password_72_bytes


def test_asignar_rol_request_vence_en_valido():
    ahora_utc = datetime.now(timezone.utc)
    futuro = ahora_utc + timedelta(days=30)
    req = AsignarRolRequest(rol="MECANICO", vence_en=futuro)
    assert req.vence_en == futuro
    assert req.rol == "MECANICO"


def test_asignar_rol_request_vence_en_none():
    req = AsignarRolRequest(rol="ADMIN", vence_en=None)
    assert req.vence_en is None


def test_asignar_rol_request_rechaza_vence_en_sin_zona_horaria():
    naive_future = datetime.now() + timedelta(days=5)
    with pytest.raises(ValidationError) as exc_info:
        AsignarRolRequest(rol="RECEPCION", vence_en=naive_future)
    assert "zona horaria" in str(exc_info.value)


def test_asignar_rol_request_rechaza_vence_en_pasado():
    pasado_con_tz = datetime.now(timezone.utc) - timedelta(days=1)
    with pytest.raises(ValidationError) as exc_info:
        AsignarRolRequest(rol="RECEPCION", vence_en=pasado_con_tz)
    assert "fecha futura" in str(exc_info.value)


def test_asignar_rol_request_rechaza_extra_fields():
    with pytest.raises(ValidationError):
        AsignarRolRequest(rol="ADMIN", campo_extra="invalido")
