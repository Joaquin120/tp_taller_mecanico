"""Pruebas de los casos de uso del ciclo de vida de las órdenes (RN-10 a RN-19)."""

from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select

from app.modules.ordenes.models import (
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.ordenes.schemas import ItemOrdenRequest, OrdenCrearRequest
from app.modules.ordenes.service import OrdenService, avisar_cliente_simulado
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.repuestos.models import MovimientoStock, Repuesto
from test.infra_sqlite import SesionFalsa, esquema_sqlite
from test.ordenes_fixtures import (
    actor_admin,
    actor_cliente,
    actor_mecanico,
    actor_recepcion,
    sembrar_escenario,
    sembrar_orden,
)


@pytest.fixture
async def escenario():
    generador = esquema_sqlite()
    sesion: SesionFalsa = next(generador)
    try:
        datos = await sembrar_escenario(sesion)
        yield sesion, datos
    finally:
        generador.close()


def _dto(vehiculo_id: int, *items: tuple[int, int]) -> OrdenCrearRequest:
    return OrdenCrearRequest(
        vehiculo_id=vehiculo_id,
        falla="Ruido en el motor",
        items=[
            ItemOrdenRequest(repuesto_id=repuesto_id, cantidad=cantidad)
            for repuesto_id, cantidad in items
        ],
    )


async def _stock(sesion: SesionFalsa, repuesto_id: int) -> int:
    sesion._sync.expire_all()
    resultado = await sesion.execute(
        select(Repuesto.stock).where(Repuesto.id == repuesto_id)
    )
    return resultado.scalar_one()


# --------------------------------------------------------------------------- #
# Catálogo de estados
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_listar_estados_respeta_el_orden_del_catalogo(escenario) -> None:
    sesion, _datos = escenario

    estados = await OrdenService.listar_estados(OrdenesUnitOfWork(sesion))

    assert [estado.codigo for estado in estados] == [
        "PENDIENTE",
        "EN_REPARACION",
        "TERMINADA",
        "CANCELADA",
    ]
    assert [estado.es_final for estado in estados] == [False, False, True, True]


# --------------------------------------------------------------------------- #
# Alta de orden (RN-10)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_crear_orden_calcula_total_y_copia_precios(escenario) -> None:
    sesion, datos = escenario

    response = await OrdenService.crear_orden(
        _dto(datos["vehiculo"].id, (datos["repuesto_1"].id, 2), (datos["repuesto_3"].id, 1)),
        actor_recepcion(datos["recepcion"].id),
        OrdenesUnitOfWork(sesion),
    )

    assert response.estado == "PENDIENTE"
    assert response.mecanico_id is None
    assert response.patente == "AA123BB"
    assert response.cliente == "Laura Gómez"
    assert response.total == Decimal("250.00")
    assert [(item.codigo, item.cantidad) for item in response.items] == [
        ("REP-001", 2),
        ("REP-003", 1),
    ]
    assert [item.subtotal for item in response.items] == [
        Decimal("200.00"),
        Decimal("50.00"),
    ]
    assert len(response.historial) == 1
    assert response.historial[0].desde_estado is None
    assert response.historial[0].hasta_estado == "PENDIENTE"
    assert response.historial[0].usuario_id == datos["recepcion"].id

    # Un único commit del UoW y filas realmente persistidas.
    assert sesion.contador_commits == 1
    assert sesion.contar(OrdenTrabajo) == 1
    assert sesion.contar(ItemOrden) == 2
    assert sesion.contar(HistorialEstadoOrden) == 1


@pytest.mark.asyncio
async def test_crear_orden_sin_catalogo_de_estados_da_409() -> None:
    generador = esquema_sqlite()
    sesion: SesionFalsa = next(generador)
    try:
        datos = await sembrar_escenario(sesion)
        sesion._sync.execute(HistorialEstadoOrden.__table__.delete())
        sesion._sync.execute(OrdenTrabajo.__table__.delete())
        sesion._sync.execute(
            __import__(
                "app.modules.ordenes.models", fromlist=["EstadoOrden"]
            ).EstadoOrden.__table__.delete()
        )
        sesion.confirmar_siembra()

        with pytest.raises(HTTPException) as excinfo:
            await OrdenService.crear_orden(
                _dto(datos["vehiculo"].id, (datos["repuesto_1"].id, 1)),
                actor_recepcion(datos["recepcion"].id),
                OrdenesUnitOfWork(sesion),
            )

        assert excinfo.value.status_code == 409
        assert "PENDIENTE" in excinfo.value.detail
        assert sesion.contar(OrdenTrabajo) == 0
    finally:
        generador.close()


@pytest.mark.asyncio
async def test_crear_orden_con_vehiculo_inexistente_da_409(escenario) -> None:
    sesion, datos = escenario

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.crear_orden(
            _dto(9999, (datos["repuesto_1"].id, 1)),
            actor_recepcion(datos["recepcion"].id),
            OrdenesUnitOfWork(sesion),
        )

    assert excinfo.value.status_code == 409
    assert "vehículo" in excinfo.value.detail.lower()
    assert sesion.contar(OrdenTrabajo) == 0


@pytest.mark.asyncio
async def test_crear_orden_con_repuesto_inexistente_no_deja_nada(escenario) -> None:
    sesion, datos = escenario

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.crear_orden(
            _dto(
                datos["vehiculo"].id,
                (datos["repuesto_1"].id, 1),
                (9999, 3),
            ),
            actor_recepcion(datos["recepcion"].id),
            OrdenesUnitOfWork(sesion),
        )

    assert excinfo.value.status_code == 409
    assert "repuesto" in excinfo.value.detail.lower()
    assert sesion.contar(OrdenTrabajo) == 0
    assert sesion.contar(ItemOrden) == 0
    assert sesion.contar(HistorialEstadoOrden) == 0
    assert sesion.contador_commits == 0


# --------------------------------------------------------------------------- #
# Listados (RN-17)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_listar_ordenes_pagina_y_filtra_por_estado(escenario) -> None:
    sesion, datos = escenario
    primera = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="PENDIENTE"
    )
    segunda = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="EN_REPARACION"
    )
    tercera = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="PENDIENTE"
    )
    uow = OrdenesUnitOfWork(sesion)

    pagina_1 = await OrdenService.listar_ordenes(None, 1, 2, uow)
    pagina_2 = await OrdenService.listar_ordenes(None, 2, 2, uow)
    pendientes = await OrdenService.listar_ordenes("PENDIENTE", 1, 20, uow)

    assert pagina_1.total == 3
    assert pagina_1.pages == 2
    assert [orden.id for orden in pagina_1.items] == [tercera.id, segunda.id]
    assert [orden.id for orden in pagina_2.items] == [primera.id]
    assert [orden.id for orden in pendientes.items] == [tercera.id, primera.id]

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.listar_ordenes(None, 4, 2, uow)
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_listar_mis_ordenes_solo_devuelve_las_propias(escenario) -> None:
    sesion, datos = escenario
    propia = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id
    )
    await sembrar_orden(sesion, datos["vehiculo_ajeno"].id, datos["recepcion"].id)

    pagina = await OrdenService.listar_mis_ordenes(
        actor_cliente(datos["cliente_user"].id), 1, 20, OrdenesUnitOfWork(sesion)
    )

    assert pagina.total == 1
    assert [orden.id for orden in pagina.items] == [propia.id]
    assert pagina.items[0].patente == "AA123BB"


@pytest.mark.asyncio
async def test_listar_mis_ordenes_vacio_para_un_usuario_sin_vehiculos(
    escenario,
) -> None:
    sesion, _datos = escenario

    pagina = await OrdenService.listar_mis_ordenes(
        actor_cliente(999), 1, 20, OrdenesUnitOfWork(sesion)
    )

    assert pagina.total == 0
    assert pagina.items == []
    assert pagina.pages == 1


# --------------------------------------------------------------------------- #
# Detalle (RN-08, RN-17)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_detalle_lo_ve_el_duenio_y_el_personal_pero_no_un_tercero(
    escenario,
) -> None:
    sesion, datos = escenario
    orden = await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        items=[(datos["repuesto_1"], 2)],
    )
    uow = OrdenesUnitOfWork(sesion)

    del_duenio = await OrdenService.obtener_orden(
        orden.id, actor_cliente(datos["cliente_user"].id), uow
    )
    del_personal = await OrdenService.obtener_orden(
        orden.id, actor_recepcion(datos["recepcion"].id), uow
    )

    assert del_duenio.patente == "AA123BB"
    assert del_duenio.total == Decimal("200.00")
    assert del_personal.id == orden.id

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.obtener_orden(orden.id, actor_cliente(999), uow)
    assert excinfo.value.status_code == 403

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.obtener_orden(9999, actor_admin(1), uow)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_detalle_tiene_consultas_fijas_sin_importar_los_items(
    escenario,
) -> None:
    """Cero N+1: 2 ítems y 4 ítems emiten la misma cantidad de SELECT."""
    sesion, datos = escenario
    orden_corta = await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        mecanico_id=datos["mecanico"].id,
        items=[(datos["repuesto_1"], 1), (datos["repuesto_2"], 1)],
    )
    orden_larga = await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        mecanico_id=datos["mecanico"].id,
        items=[
            (datos["repuesto_1"], 1),
            (datos["repuesto_2"], 1),
            (datos["repuesto_3"], 1),
            (datos["repuesto_4"], 1),
        ],
    )
    uow = OrdenesUnitOfWork(sesion)

    consultas: list[str] = []

    def _contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)

    event.listen(sesion.engine, "before_cursor_execute", _contar)
    try:
        consultas.clear()
        detalle_corto = await OrdenService.obtener_orden(
            orden_corta.id, actor_admin(1), uow
        )
        del_corta = len(consultas)

        consultas.clear()
        detalle_largo = await OrdenService.obtener_orden(
            orden_larga.id, actor_admin(1), uow
        )
        del_larga = len(consultas)
    finally:
        event.remove(sesion.engine, "before_cursor_execute", _contar)

    assert len(detalle_corto.items) == 2
    assert len(detalle_largo.items) == 4
    assert del_corta == del_larga, (
        f"hay N+1: {del_corta} consultas con 2 ítems y {del_larga} con 4"
    )
    assert del_corta <= 8, f"demasiadas consultas para el detalle: {del_corta}"


# --------------------------------------------------------------------------- #
# Inicio (RN-11)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_iniciar_orden_autoasigna_mecanico_y_registra_historial(escenario) -> None:
    sesion, datos = escenario
    orden = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="PENDIENTE"
    )
    actor = actor_mecanico(datos["mecanico"].id)

    response = await OrdenService.iniciar_orden(
        orden.id, actor, OrdenesUnitOfWork(sesion)
    )

    assert response.estado == "EN_REPARACION"
    assert response.mecanico_id == datos["mecanico"].id
    assert [registro.hasta_estado for registro in response.historial] == [
        "PENDIENTE",
        "EN_REPARACION",
    ]
    assert sesion.contador_commits == 1
    assert sesion.contar(HistorialEstadoOrden) == 2


@pytest.mark.asyncio
async def test_iniciar_orden_que_no_esta_pendiente_da_409(escenario) -> None:
    sesion, datos = escenario
    orden = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="EN_REPARACION"
    )

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.iniciar_orden(
            orden.id,
            actor_mecanico(datos["mecanico"].id),
            OrdenesUnitOfWork(sesion),
        )

    assert excinfo.value.status_code == 409
    assert sesion.contador_commits == 0

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.iniciar_orden(
            9999, actor_mecanico(datos["mecanico"].id), OrdenesUnitOfWork(sesion)
        )
    assert excinfo.value.status_code == 404


# --------------------------------------------------------------------------- #
# Terminación atómica con descuento de stock (RN-13)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_terminar_orden_descuenta_stock_y_registra_todo(escenario) -> None:
    sesion, datos = escenario
    orden = await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        estado="EN_REPARACION",
        mecanico_id=datos["mecanico"].id,
        items=[(datos["repuesto_1"], 2), (datos["repuesto_2"], 1)],
    )
    actor = actor_mecanico(datos["mecanico"].id)

    response = await OrdenService.terminar_orden(
        orden.id, actor, OrdenesUnitOfWork(sesion)
    )

    assert response.estado == "TERMINADA"
    assert [registro.hasta_estado for registro in response.historial] == [
        "PENDIENTE",
        "TERMINADA",
    ]
    assert await _stock(sesion, datos["repuesto_1"].id) == 8
    assert await _stock(sesion, datos["repuesto_2"].id) == 2

    movimientos = sesion.listar(MovimientoStock)
    assert len(movimientos) == 2
    assert {movimiento.repuesto_id for movimiento in movimientos} == {
        datos["repuesto_1"].id,
        datos["repuesto_2"].id,
    }
    assert all(movimiento.orden_id == orden.id for movimiento in movimientos)
    assert all(movimiento.usuario_id == actor.id for movimiento in movimientos)
    assert sorted(movimiento.cantidad for movimiento in movimientos) == [-2, -1]

    # Un único commit para stock + movimientos + historial + estado.
    assert sesion.contador_commits == 1


@pytest.mark.asyncio
async def test_terminar_orden_sin_stock_revierte_todo(escenario) -> None:
    sesion, datos = escenario
    orden = await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        estado="EN_REPARACION",
        mecanico_id=datos["mecanico"].id,
        items=[(datos["repuesto_1"], 1), (datos["repuesto_2"], 5)],
    )
    historial_previo = sesion.contar(HistorialEstadoOrden)

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.terminar_orden(
            orden.id,
            actor_mecanico(datos["mecanico"].id),
            OrdenesUnitOfWork(sesion),
        )

    assert excinfo.value.status_code == 409
    assert "REP-002" in excinfo.value.detail

    # Ni stock, ni movimientos, ni historial, ni estado: rollback total.
    assert await _stock(sesion, datos["repuesto_1"].id) == 10
    assert await _stock(sesion, datos["repuesto_2"].id) == 3
    assert sesion.contar(MovimientoStock) == 0
    assert sesion.contar(HistorialEstadoOrden) == historial_previo
    assert sesion.contador_commits == 0

    sesion._sync.expire_all()
    estado = await sesion.execute(
        select(OrdenTrabajo.estado).where(OrdenTrabajo.id == orden.id)
    )
    assert estado.scalar_one() == "EN_REPARACION"


@pytest.mark.asyncio
async def test_terminar_orden_exige_mecanico_asignado_o_admin(escenario) -> None:
    sesion, datos = escenario
    orden = await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        estado="EN_REPARACION",
        mecanico_id=datos["mecanico"].id,
        items=[(datos["repuesto_1"], 1)],
    )

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.terminar_orden(
            orden.id,
            actor_mecanico(datos["otro_mecanico"].id),
            OrdenesUnitOfWork(sesion),
        )
    assert excinfo.value.status_code == 403

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.terminar_orden(
            orden.id, actor_recepcion(datos["recepcion"].id), OrdenesUnitOfWork(sesion)
        )
    assert excinfo.value.status_code == 403

    assert sesion.contar(MovimientoStock) == 0
    assert await _stock(sesion, datos["repuesto_1"].id) == 10

    # El administrador sí puede terminar una orden ajena.
    response = await OrdenService.terminar_orden(
        orden.id, actor_admin(datos["admin"].id), OrdenesUnitOfWork(sesion)
    )
    assert response.estado == "TERMINADA"
    assert await _stock(sesion, datos["repuesto_1"].id) == 9


@pytest.mark.asyncio
async def test_terminar_orden_fuera_de_en_reparacion_da_409(escenario) -> None:
    sesion, datos = escenario
    orden = await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        estado="PENDIENTE",
        mecanico_id=datos["mecanico"].id,
        items=[(datos["repuesto_1"], 1)],
    )

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.terminar_orden(
            orden.id,
            actor_mecanico(datos["mecanico"].id),
            OrdenesUnitOfWork(sesion),
        )

    assert excinfo.value.status_code == 409
    assert sesion.contar(MovimientoStock) == 0


# --------------------------------------------------------------------------- #
# Cancelación (RN-11, RN-12)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cancelar_evalua_permisos_antes_que_estado(escenario) -> None:
    sesion, datos = escenario
    orden = await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        estado="TERMINADA",
        items=[(datos["repuesto_1"], 1)],
    )
    uow = OrdenesUnitOfWork(sesion)

    # Un tercero no autorizado recibe 403 aunque el estado también sea inválido.
    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.cancelar_orden(orden.id, actor_cliente(999), uow)
    assert excinfo.value.status_code == 403

    # El dueño sí está autorizado, así que ahora el conflicto de estado es 409.
    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.cancelar_orden(
            orden.id, actor_cliente(datos["cliente_user"].id), uow
        )
    assert excinfo.value.status_code == 409

    with pytest.raises(HTTPException) as excinfo:
        await OrdenService.cancelar_orden(9999, actor_admin(1), uow)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_cancelar_pendiente_por_el_duenio_y_por_recepcion(escenario) -> None:
    sesion, datos = escenario
    propia = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="PENDIENTE"
    )
    otra = await sembrar_orden(
        sesion, datos["vehiculo"].id, datos["recepcion"].id, estado="PENDIENTE"
    )
    uow = OrdenesUnitOfWork(sesion)

    por_duenio = await OrdenService.cancelar_orden(
        propia.id, actor_cliente(datos["cliente_user"].id), uow
    )
    por_recepcion = await OrdenService.cancelar_orden(
        otra.id, actor_recepcion(datos["recepcion"].id), uow
    )

    assert por_duenio.estado == "CANCELADA"
    assert por_recepcion.estado == "CANCELADA"
    assert sesion.contar(HistorialEstadoOrden) == 4


# --------------------------------------------------------------------------- #
# Aviso simulado (Ej. 8)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_aviso_simulado_duerme_y_registra_log(monkeypatch, caplog) -> None:
    esperas: list[float] = []

    async def _sleep_falso(segundos: float) -> None:
        esperas.append(segundos)

    monkeypatch.setattr("app.modules.ordenes.service.asyncio.sleep", _sleep_falso)

    with caplog.at_level("INFO", logger="app.modules.ordenes.service"):
        await avisar_cliente_simulado(7, "Laura Gómez")

    assert esperas == [0.5]
    assert "orden 7" in caplog.text
    assert "Laura Gómez" in caplog.text


@pytest.mark.asyncio
async def test_aviso_simulado_no_propaga_errores(monkeypatch) -> None:
    async def _sleep_roto(segundos: float) -> None:
        raise RuntimeError("falla del notificador")

    monkeypatch.setattr("app.modules.ordenes.service.asyncio.sleep", _sleep_roto)

    # No debe levantar: la respuesta HTTP ya se envió.
    await avisar_cliente_simulado(1, "Cliente")
