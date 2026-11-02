"""Pruebas del Unit of Work del módulo de órdenes (DD-06, RN-15).

Verifican que:
- los siete repositorios comparten exactamente la misma sesión;
- un bloque exitoso produce un único `commit`;
- una excepción revierte todo el trabajo y no deja filas a medias;
- ningún repositorio llama a `commit()` por su cuenta.
"""

from decimal import Decimal

import pytest

from app.modules.ordenes.models import (
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.repuestos.models import MovimientoStock
from test.infra_sqlite import SesionFalsa, esquema_sqlite
from test.ordenes_fixtures import sembrar_escenario

REPOSITORIOS = (
    "estados",
    "ordenes",
    "items",
    "historial",
    "vehiculos",
    "repuestos",
    "movimientos",
)


@pytest.fixture
async def sesion():
    generador = esquema_sqlite()
    base: SesionFalsa = next(generador)
    try:
        yield base
    finally:
        generador.close()


def test_expone_los_siete_repositorios_sobre_la_misma_sesion(
    sesion: SesionFalsa,
) -> None:
    uow = OrdenesUnitOfWork(sesion)

    for nombre in REPOSITORIOS:
        repositorio = getattr(uow, nombre)
        assert repositorio.session is sesion, f"{nombre} no comparte la sesión del UoW"

    assert uow.session is sesion


@pytest.mark.asyncio
async def test_bloque_exitoso_hace_un_unico_commit(sesion: SesionFalsa) -> None:
    datos = await sembrar_escenario(sesion)
    uow = OrdenesUnitOfWork(sesion)

    async with uow:
        orden = await uow.ordenes.add(
            OrdenTrabajo(
                vehiculo_id=datos["vehiculo"].id,
                estado="PENDIENTE",
                falla="Falla",
                total=Decimal("100.00"),
            )
        )
        await uow.items.add(
            ItemOrden(
                orden_id=orden.id,
                repuesto_id=datos["repuesto_1"].id,
                cantidad=1,
                precio_unitario=datos["repuesto_1"].precio,
            )
        )
        await uow.historial.add(
            HistorialEstadoOrden(
                orden_id=orden.id,
                desde_estado=None,
                hasta_estado="PENDIENTE",
                usuario_id=datos["recepcion"].id,
            )
        )

    assert sesion.contador_commits == 1
    assert sesion.contar(OrdenTrabajo) == 1
    assert sesion.contar(ItemOrden) == 1
    assert sesion.contar(HistorialEstadoOrden) == 1


@pytest.mark.asyncio
async def test_excepcion_revierte_todo_el_bloque(sesion: SesionFalsa) -> None:
    datos = await sembrar_escenario(sesion)
    ordenes_previas = sesion.contar(OrdenTrabajo)
    uow = OrdenesUnitOfWork(sesion)

    with pytest.raises(RuntimeError):
        async with uow:
            orden = await uow.ordenes.add(
                OrdenTrabajo(
                    vehiculo_id=datos["vehiculo"].id,
                    estado="PENDIENTE",
                    falla="Falla",
                    total=Decimal("250.00"),
                )
            )
            await uow.items.add(
                ItemOrden(
                    orden_id=orden.id,
                    repuesto_id=datos["repuesto_2"].id,
                    cantidad=2,
                    precio_unitario=datos["repuesto_2"].precio,
                )
            )
            await uow.movimientos.add(
                MovimientoStock(
                    repuesto_id=datos["repuesto_2"].id,
                    orden_id=orden.id,
                    usuario_id=datos["recepcion"].id,
                    cantidad=-2,
                    motivo="Salida de prueba",
                )
            )
            raise RuntimeError("falla simulada de mitad de transacción")

    assert sesion.contador_commits == 0
    assert sesion.contar(OrdenTrabajo) == ordenes_previas
    assert sesion.contar(ItemOrden) == 0
    assert sesion.contar(MovimientoStock) == 0


@pytest.mark.asyncio
async def test_los_repositorios_nunca_llaman_a_commit(sesion: SesionFalsa) -> None:
    datos = await sembrar_escenario(sesion)
    uow = OrdenesUnitOfWork(sesion)
    commits_antes = sesion.contador_commits

    orden = await uow.ordenes.add(
        OrdenTrabajo(
            vehiculo_id=datos["vehiculo"].id,
            estado="PENDIENTE",
            falla="Falla",
            total=Decimal("10.00"),
        )
    )
    item = await uow.items.add(
        ItemOrden(
            orden_id=orden.id,
            repuesto_id=datos["repuesto_4"].id,
            cantidad=1,
            precio_unitario=datos["repuesto_4"].precio,
        )
    )
    await uow.ordenes.update(orden)
    await uow.items.update(item)
    await uow.historial.add(
        HistorialEstadoOrden(
            orden_id=orden.id,
            desde_estado=None,
            hasta_estado="PENDIENTE",
            usuario_id=datos["recepcion"].id,
        )
    )

    # Todo el trabajo anterior sigue sin confirmar: el commit es del UoW.
    assert sesion.contador_commits == commits_antes
    assert sesion._sync.in_transaction() is True
