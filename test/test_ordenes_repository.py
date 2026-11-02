"""Pruebas de repositorios y carga anticipada del módulo de órdenes."""

import pytest

from app.modules.ordenes.models import HistorialEstadoOrden
from app.modules.ordenes.repository import (
    EstadoOrdenRepository,
    HistorialEstadoOrdenRepository,
    OrdenTrabajoRepository,
)
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.repuestos.models import MovimientoStock
from test.infra_sqlite import SesionFalsa, esquema_sqlite
from test.ordenes_fixtures import sembrar_cliente, sembrar_orden, sembrar_escenario


@pytest.fixture
async def sesion():
    generador = esquema_sqlite()
    base: SesionFalsa = next(generador)
    try:
        yield base
    finally:
        generador.close()


@pytest.mark.asyncio
async def test_catalogo_se_ordena_por_posicion_y_es_solo_lectura(
    sesion: SesionFalsa,
) -> None:
    await sembrar_escenario(sesion)
    repositorio = EstadoOrdenRepository(sesion)

    estados = await repositorio.listar_por_posicion()

    assert [estado.codigo for estado in estados] == [
        "PENDIENTE",
        "EN_REPARACION",
        "TERMINADA",
        "CANCELADA",
    ]
    assert await repositorio.contar() == 4
    assert (await repositorio.get_by_codigo("TERMINADA")).es_final is True
    assert await repositorio.get_by_codigo("NO_EXISTE") is None

    for metodo in ("add", "update", "delete", "soft_delete"):
        assert not hasattr(repositorio, metodo)


@pytest.mark.asyncio
async def test_detalle_precarga_vehiculo_cliente_items_repuestos_e_historial(
    sesion: SesionFalsa,
) -> None:
    datos = await sembrar_escenario(sesion)
    orden = await sembrar_orden(
        sesion,
        vehiculo_id=datos["vehiculo"].id,
        usuario_id=datos["recepcion"].id,
        estado="EN_REPARACION",
        mecanico_id=datos["mecanico"].id,
        items=[
            (datos["repuesto_1"], 2),
            (datos["repuesto_2"], 1),
        ],
    )

    detalle = await OrdenTrabajoRepository(sesion).get_detalle(orden.id)

    assert detalle is not None
    assert detalle.vehiculo.patente == "AA123BB"
    assert detalle.vehiculo.cliente.nombre == "Laura Gómez"
    assert detalle.mecanico is not None
    assert detalle.mecanico.id == datos["mecanico"].id
    assert [item.repuesto.codigo for item in detalle.items] == ["REP-001", "REP-002"]
    assert [registro.hasta_estado for registro in detalle.historial_estados] == [
        "PENDIENTE"
    ]


@pytest.mark.asyncio
async def test_listar_filtra_por_estado_y_pagina(sesion: SesionFalsa) -> None:
    datos = await sembrar_escenario(sesion)
    primera = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="PENDIENTE"
    )
    segunda = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="EN_REPARACION"
    )
    repositorio = OrdenTrabajoRepository(sesion)

    todas = await repositorio.listar(None, offset=0, limit=10)
    pendientes = await repositorio.listar("PENDIENTE", offset=0, limit=10)
    pagina_1 = await repositorio.listar(None, offset=0, limit=1)

    assert [orden.id for orden in todas] == [segunda.id, primera.id]
    assert [orden.id for orden in pendientes] == [primera.id]
    assert [orden.id for orden in pagina_1] == [segunda.id]
    assert await repositorio.contar_por_estado(None) == 2
    assert await repositorio.contar_por_estado("PENDIENTE") == 1


@pytest.mark.asyncio
async def test_listar_por_cliente_usuario_solo_devuelve_las_propias(
    sesion: SesionFalsa,
) -> None:
    datos = await sembrar_escenario(sesion)
    propia = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id
    )
    await sembrar_orden(
        sesion, datos["vehiculo_ajeno"].id, datos["recepcion"].id
    )
    repositorio = OrdenTrabajoRepository(sesion)

    propias = await repositorio.listar_por_cliente_usuario(
        datos["cliente_user"].id, offset=0, limit=10
    )

    assert [orden.id for orden in propias] == [propia.id]
    assert await repositorio.contar_por_cliente_usuario(datos["cliente_user"].id) == 1

    sin_cliente = await sembrar_cliente(
        sesion, documento="99999999", usuario_id=None, nombre="Sin usuario"
    )
    assert sin_cliente.usuario_id is None
    assert await repositorio.contar_por_cliente_usuario(999) == 0


@pytest.mark.asyncio
async def test_contar_ordenes_abiertas_ignora_estados_finales(
    sesion: SesionFalsa,
) -> None:
    datos = await sembrar_escenario(sesion)
    await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="PENDIENTE"
    )
    await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="TERMINADA"
    )
    repositorio = OrdenTrabajoRepository(sesion)

    assert await repositorio.contar_ordenes_abiertas(datos["vehiculo"].id) == 1


@pytest.mark.asyncio
async def test_historial_y_movimientos_bloquean_update_y_delete(
    sesion: SesionFalsa,
) -> None:
    uow = OrdenesUnitOfWork(sesion)
    historial = HistorialEstadoOrden(
        orden_id=1,
        desde_estado=None,
        hasta_estado="PENDIENTE",
        usuario_id=1,
    )
    movimiento = MovimientoStock(
        repuesto_id=1,
        orden_id=1,
        usuario_id=1,
        cantidad=-1,
        motivo="Salida",
    )

    for repositorio, entidad in (
        (uow.historial, historial),
        (uow.movimientos, movimiento),
    ):
        with pytest.raises(NotImplementedError):
            await repositorio.update(entidad)
        with pytest.raises(NotImplementedError):
            await repositorio.delete(entidad)

    assert isinstance(uow.historial, HistorialEstadoOrdenRepository)
