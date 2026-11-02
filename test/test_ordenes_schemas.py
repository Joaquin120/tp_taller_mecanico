"""Pruebas de los contratos Pydantic del módulo de órdenes (RN-10, RN-18)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.ordenes.schemas import (
    HistorialEstadoResponse,
    ItemOrdenRequest,
    ItemOrdenResponse,
    OrdenCrearRequest,
    OrdenResponse,
    OrdenResumenResponse,
)


def _payload_valido() -> dict:
    return {
        "vehiculo_id": 1,
        "falla": "Ruido en el motor",
        "items": [{"repuesto_id": 1, "cantidad": 2}],
    }


def test_payload_valido_y_normalizacion_de_falla() -> None:
    dto = OrdenCrearRequest(**{**_payload_valido(), "falla": "  Ruido leve  "})

    assert dto.falla == "Ruido leve"
    assert dto.items[0].cantidad == 2


@pytest.mark.parametrize(
    "campo_extra, valor",
    [
        ("total", "100.00"),
        ("estado", "TERMINADA"),
        ("mecanico_id", 3),
        ("precio_unitario", "10.00"),
        ("subtotal", "20.00"),
        ("cliente", "Laura"),
    ],
)
def test_campos_extra_en_la_orden_dan_422(campo_extra: str, valor) -> None:
    with pytest.raises(ValidationError):
        OrdenCrearRequest(**{**_payload_valido(), campo_extra: valor})


@pytest.mark.parametrize(
    "campo_extra, valor",
    [("precio_unitario", "10.00"), ("subtotal", "20.00"), ("codigo", "REP-001")],
)
def test_campos_extra_en_el_item_dan_422(campo_extra: str, valor) -> None:
    with pytest.raises(ValidationError):
        OrdenCrearRequest(
            vehiculo_id=1,
            falla="Falla",
            items=[{"repuesto_id": 1, "cantidad": 1, campo_extra: valor}],
        )


def test_items_vacios_dan_422() -> None:
    with pytest.raises(ValidationError):
        OrdenCrearRequest(vehiculo_id=1, falla="Falla", items=[])


@pytest.mark.parametrize("cantidad", [0, -1])
def test_cantidad_no_positiva_da_422(cantidad: int) -> None:
    with pytest.raises(ValidationError):
        ItemOrdenRequest(repuesto_id=1, cantidad=cantidad)


def test_repuesto_repetido_da_422() -> None:
    with pytest.raises(ValidationError):
        OrdenCrearRequest(
            vehiculo_id=1,
            falla="Falla",
            items=[
                {"repuesto_id": 1, "cantidad": 1},
                {"repuesto_id": 1, "cantidad": 2},
            ],
        )


@pytest.mark.parametrize("falla", ["", "   ", "x" * 501])
def test_falla_fuera_de_rango_da_422(falla: str) -> None:
    with pytest.raises(ValidationError):
        OrdenCrearRequest(
            vehiculo_id=1,
            falla=falla,
            items=[{"repuesto_id": 1, "cantidad": 1}],
        )


def test_respuestas_serializan_decimal_y_no_aceptan_extra() -> None:
    item = ItemOrdenResponse(
        repuesto_id=1,
        codigo="REP-001",
        descripcion="Filtro",
        cantidad=2,
        precio_unitario=Decimal("100.00"),
        subtotal=Decimal("200.00"),
    )
    response = OrdenResponse(
        id=1,
        estado="PENDIENTE",
        patente="AA123BB",
        creada_en="2026-01-01T12:00:00+00:00",
        total=Decimal("200.00"),
        mecanico_id=None,
        falla="Falla",
        cliente="Laura",
        items=[item],
        historial=[
            HistorialEstadoResponse(
                desde_estado=None,
                hasta_estado="PENDIENTE",
                usuario_id=2,
                cuando="2026-01-01T12:00:00+00:00",
            )
        ],
    )

    assert response.total == Decimal("200.00")
    assert response.items[0].subtotal == Decimal("200.00")

    with pytest.raises(ValidationError):
        OrdenResumenResponse(
            id=1,
            estado="PENDIENTE",
            vehiculo_id=1,
            patente="AA123BB",
            mecanico_id=None,
            falla="Falla",
            creada_en="2026-01-01T12:00:00+00:00",
            total=Decimal("200.00"),
            password_hash="no-debe-viajar",
        )
