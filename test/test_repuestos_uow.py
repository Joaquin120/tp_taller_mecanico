"""Unit of Work del módulo de repuestos: sesión compartida y atomicidad."""

from decimal import Decimal

import pytest

from app.modules.repuestos.models import Repuesto
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork
from test.infra_sqlite import SesionFalsa, esquema_sqlite


@pytest.fixture
async def sesion():
    gen = esquema_sqlite()
    base: SesionFalsa = next(gen)
    try:
        yield base
    finally:
        gen.close()


def test_los_tres_repositorios_comparten_la_misma_sesion(sesion: SesionFalsa):
    uow = RepuestosUnitOfWork(sesion)

    assert uow.repuestos.session is sesion
    assert uow.movimientos.session is sesion
    assert uow.precios.session is sesion


@pytest.mark.asyncio
async def test_salida_limpia_confirma_una_sola_vez(sesion: SesionFalsa):
    uow = RepuestosUnitOfWork(sesion)

    async with uow:
        await uow.repuestos.add(
            Repuesto(codigo="R-001", descripcion="Filtro", precio=Decimal("10.00"), stock=0)
        )

    assert sesion.contador_commits == 1
    assert sesion.contar(Repuesto) == 1


@pytest.mark.asyncio
async def test_excepcion_revierte_todo_sin_commit(sesion: SesionFalsa):
    uow = RepuestosUnitOfWork(sesion)

    with pytest.raises(RuntimeError):
        async with uow:
            await uow.repuestos.add(
                Repuesto(codigo="R-001", descripcion="Filtro", precio=Decimal("10.00"), stock=0)
            )
            raise RuntimeError("fallo simulado")

    assert sesion.contador_commits == 0
    assert sesion.contar(Repuesto) == 0
