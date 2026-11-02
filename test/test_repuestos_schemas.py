"""Contratos del módulo de repuestos: `extra="forbid"`, precios y longitudes."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.repuestos.schemas import (
    HistorialPrecioResponse,
    MovimientoStockResponse,
    ReponerStockRequest,
    RepuestoCreate,
    RepuestoUpdate,
)


def test_alta_rechaza_campo_extra():
    with pytest.raises(ValidationError):
        RepuestoCreate(
            codigo="R-001",
            descripcion="Filtro de aceite",
            precio="10.00",
            stock_inicial=1,
            stock=5,  # el stock no viaja por contrato (RN-14)
        )


@pytest.mark.parametrize("precio", ["0", "-1", "10.999"])
def test_alta_rechaza_precio_no_positivo_o_con_mas_de_dos_decimales(precio: str):
    with pytest.raises(ValidationError):
        RepuestoCreate(codigo="R-001", descripcion="Filtro", precio=precio)


def test_alta_acepta_precio_de_dos_decimales():
    dto = RepuestoCreate(codigo=" R-001 ", descripcion="  Filtro  ", precio="10.50")
    assert dto.codigo == "R-001"
    assert dto.descripcion == "Filtro"
    assert dto.precio == Decimal("10.50")
    assert dto.stock_inicial == 0


@pytest.mark.parametrize(
    "codigo",
    ["", "   ", "X" * 51],
)
def test_alta_rechaza_codigo_invalido(codigo: str):
    with pytest.raises(ValidationError):
        RepuestoCreate(codigo=codigo, descripcion="Filtro", precio="10.00")


def test_alta_rechaza_descripcion_vacia_o_demasiado_larga():
    with pytest.raises(ValidationError):
        RepuestoCreate(codigo="R-001", descripcion="   ", precio="10.00")
    with pytest.raises(ValidationError):
        RepuestoCreate(codigo="R-001", descripcion="D" * 256, precio="10.00")


def test_actualizacion_exige_al_menos_un_campo():
    with pytest.raises(ValidationError):
        RepuestoUpdate()


def test_actualizacion_rechaza_stock():
    with pytest.raises(ValidationError):
        RepuestoUpdate(precio="12.00", stock=9)


def test_actualizacion_rechaza_precio_no_positivo():
    with pytest.raises(ValidationError):
        RepuestoUpdate(precio="0")


def test_reposicion_exige_cantidad_positiva():
    for cantidad in (0, -1):
        with pytest.raises(ValidationError):
            ReponerStockRequest(cantidad=cantidad)
    assert ReponerStockRequest(cantidad=3).cantidad == 3


def test_respuestas_publicas_no_exponen_campos_internos():
    movimiento = MovimientoStockResponse(
        id=1,
        cantidad=2,
        motivo="ALTA",
        cuando="2026-01-01T12:00:00Z",
        usuario_id=1,
    )
    assert movimiento.orden_id is None
    assert "borrado_en" not in movimiento.model_dump()

    precio = HistorialPrecioResponse(
        id=1,
        precio_anterior="10.00",
        precio_nuevo="12.00",
        cuando="2026-01-01T12:00:00Z",
        usuario_id=1,
    )
    assert precio.precio_nuevo == Decimal("12.00")
