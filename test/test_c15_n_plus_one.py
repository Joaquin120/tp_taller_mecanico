"""Test automatizado para verificar Caso C-15 (Cero consultas N+1).

Instrumenta el motor SQLAlchemy mediante el listener `before_cursor_execute`
para contar con exactitud las sentencias SQL emitidas al consultar el detalle
de una orden con 2 ítems versus una orden con 4 ítems.
"""

from decimal import Decimal
import pytest
from sqlalchemy import event

from app.modules.ordenes.service import OrdenService
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from test.infra_sqlite import SesionFalsa, esquema_sqlite
from test.ordenes_fixtures import (
    actor_admin,
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
        try:
            next(generador)
        except StopIteration:
            pass


@pytest.mark.asyncio
async def test_c15_detalle_orden_sin_n_plus_one(escenario) -> None:
    """Verifica que el número de consultas SQL en el detalle es constante e independiente del número de ítems (C-15)."""
    sesion, datos = escenario

    # 1. Sembrar orden corta con 2 ítems
    orden_corta = await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        mecanico_id=datos["mecanico"].id,
        items=[(datos["repuesto_1"], 1), (datos["repuesto_2"], 1)],
    )

    # 2. Sembrar orden larga con 4 ítems
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
    consultas_ejecutadas: list[str] = []

    def interceptor_consultas(conn, cursor, statement, parameters, context, executemany):
        consultas_ejecutadas.append(statement)

    event.listen(sesion.engine, "before_cursor_execute", interceptor_consultas)

    try:
        # Medición Orden Corta (2 ítems)
        consultas_ejecutadas.clear()
        detalle_corto = await OrdenService.obtener_orden(
            orden_corta.id, actor_admin(1), uow
        )
        conteo_2_items = len(consultas_ejecutadas)

        # Medición Orden Larga (4 ítems)
        consultas_ejecutadas.clear()
        detalle_largo = await OrdenService.obtener_orden(
            orden_larga.id, actor_admin(1), uow
        )
        conteo_4_items = len(consultas_ejecutadas)

        print(f"\n[C-15 EVIDENCIA] Consultas para orden de 2 ítems: {conteo_2_items}")
        print(f"[C-15 EVIDENCIA] Consultas para orden de 4 ítems: {conteo_4_items}")

        assert len(detalle_corto.items) == 2
        assert len(detalle_largo.items) == 4
        assert conteo_2_items == conteo_4_items, (
            f"Existe problema de N+1: {conteo_2_items} consultas con 2 ítems vs "
            f"{conteo_4_items} consultas con 4 ítems"
        )
        assert conteo_2_items <= 8, f"Demasiadas consultas para el detalle: {conteo_2_items}"
    finally:
        event.remove(sesion.engine, "before_cursor_execute", interceptor_consultas)
