import pytest
from pydantic import ValidationError
from app.core.schemas import BaseSchema


class DummySchema(BaseSchema):
    nombre: str
    edad: int


class NestedSchema(BaseSchema):
    detalle: DummySchema


def test_base_schema_rejects_extra_fields():
    with pytest.raises(ValidationError) as exc_info:
        DummySchema(nombre="Juan", edad=30, campo_extra="no_permitido")
    
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("campo_extra",) and err["type"] == "extra_forbidden" for err in errors)


def test_base_schema_accepts_valid_fields():
    obj = DummySchema(nombre="Juan", edad=30)
    assert obj.nombre == "Juan"
    assert obj.edad == 30


def test_base_schema_nested_rejects_extra_fields():
    with pytest.raises(ValidationError) as exc_info:
        NestedSchema(detalle={"nombre": "Ana", "edad": 25, "extra": "invalido"})
    
    errors = exc_info.value.errors()
    assert any("extra" in str(err["loc"]) and err["type"] == "extra_forbidden" for err in errors)
