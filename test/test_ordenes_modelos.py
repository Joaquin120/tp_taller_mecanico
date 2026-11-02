"""Pruebas de mapeo de los modelos del módulo de órdenes (C-02 / C-08)."""

import pytest
from sqlalchemy import DateTime, Numeric

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

from app.modules.ordenes.models import (
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from test.infra_sqlite import SesionFalsa, esquema_sqlite
from test.ordenes_fixtures import sembrar_escenario, sembrar_orden


def _nombres_de_restricciones(modelo) -> set[str]:
    return {
        restriccion.name
        for restriccion in modelo.__table__.constraints
        if restriccion.name is not None
    }


def test_estado_orden_mapea_pk_posicion_unica_y_es_final() -> None:
    tabla = EstadoOrden.__table__

    assert tabla.c.codigo.primary_key is True
    assert tabla.c.posicion.unique is True
    assert tabla.c.posicion.nullable is False
    assert tabla.c.descripcion.nullable is False
    assert tabla.c.es_final.nullable is False


def test_orden_trabajo_mapea_total_numerico_y_checks() -> None:
    tabla = OrdenTrabajo.__table__
    total = tabla.c.total

    assert isinstance(total.type, Numeric)
    assert (total.type.precision, total.type.scale) == (12, 2)
    assert total.nullable is False
    assert isinstance(tabla.c.creada_en.type, DateTime)
    assert tabla.c.creada_en.type.timezone is True

    restricciones = _nombres_de_restricciones(OrdenTrabajo)
    assert "ck_orden_trabajo_total_no_negativo" in restricciones

    destinos = {
        fk.target_fullname
        for columna in ("vehiculo_id", "mecanico_id", "estado")
        for fk in tabla.c[columna].foreign_keys
    }
    assert "vehiculo.id" in destinos
    assert "usuario.id" in destinos
    assert "estado_orden.codigo" in destinos


def test_item_orden_mapea_checks_y_unicidad_compuesta() -> None:
    tabla = ItemOrden.__table__

    assert tabla.c.cantidad.nullable is False
    assert isinstance(tabla.c.precio_unitario.type, Numeric)
    assert (tabla.c.precio_unitario.type.precision, tabla.c.precio_unitario.type.scale) == (
        10,
        2,
    )

    restricciones = _nombres_de_restricciones(ItemOrden)
    assert "ck_item_orden_cantidad_positiva" in restricciones
    assert "ck_item_orden_precio_positivo" in restricciones
    assert "uq_item_orden_orden_repuesto" in restricciones


def test_historial_mapea_dos_fk_al_catalogo_y_cuando_con_zona() -> None:
    tabla = HistorialEstadoOrden.__table__

    assert tabla.c.desde_estado.nullable is True
    assert tabla.c.hasta_estado.nullable is False
    assert tabla.c.cuando.type.timezone is True

    destinos_desde = {fk.target_fullname for fk in tabla.c.desde_estado.foreign_keys}
    destinos_hasta = {fk.target_fullname for fk in tabla.c.hasta_estado.foreign_keys}
    assert destinos_desde == {"estado_orden.codigo"}
    assert destinos_hasta == {"estado_orden.codigo"}


@pytest.mark.asyncio
async def test_historial_inserta_desde_estado_nulo() -> None:
    generador = esquema_sqlite()
    sesion: SesionFalsa = next(generador)
    try:
        datos = await sembrar_escenario(sesion)
        orden = await sembrar_orden(
            sesion,
            vehiculo_id=datos["vehiculo"].id,
            usuario_id=datos["recepcion"].id,
        )

        historial = [
            fila
            for fila in sesion.listar(HistorialEstadoOrden)
            if fila.orden_id == orden.id
        ]
        assert len(historial) == 1
        assert historial[0].desde_estado is None
        assert historial[0].hasta_estado == "PENDIENTE"
    finally:
        generador.close()


def test_seed_declara_los_cuatro_estados_y_sus_finales() -> None:
    from pathlib import Path

    contenido = Path("seed.py").read_text(encoding="utf-8")

    for codigo, _descripcion, posicion, es_final in (
        ("PENDIENTE", "", 1, False),
        ("EN_REPARACION", "", 2, False),
        ("TERMINADA", "", 3, True),
        ("CANCELADA", "", 4, True),
    ):
        assert f'codigo="{codigo}"' in contenido
        assert f"posicion={posicion}" in contenido
        assert f"es_final={es_final}" in contenido
