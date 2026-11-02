"""Repositorios de repuestos sobre SQLite en memoria (lógica real, base simulada)."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Numeric

from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.repuestos.repository import (
    HistorialPrecioRepuestoRepository,
    MovimientoStockRepository,
    RepuestoRepository,
)
from test.infra_sqlite import SesionFalsa, esquema_sqlite


@pytest.fixture
async def sesion():
    gen = esquema_sqlite()
    base: SesionFalsa = next(gen)
    try:
        yield base
    finally:
        gen.close()


def test_modelo_mapea_el_esquema_existente_de_la_migracion_001():
    """Tarea 4.1: el modelo refleja lo que ya crea `001_initial_schema`."""
    columnas = Repuesto.__table__.columns

    precio = columnas["precio"].type
    assert isinstance(precio, Numeric)
    assert precio.precision == 10
    assert precio.scale == 2
    assert columnas["borrado_en"].type.timezone is True
    assert MovimientoStock.__table__.columns["cuando"].type.timezone is True
    assert HistorialPrecioRepuesto.__table__.columns["cuando"].type.timezone is True

    indice = next(
        i for i in Repuesto.__table__.indexes if i.name == "uq_repuesto_codigo_activo"
    )
    assert indice.unique is True
    assert "borrado_en IS NULL" in str(indice.dialect_options["postgresql"]["where"])


async def sembrar(
    sesion: SesionFalsa,
    codigo: str,
    descripcion: str,
    precio: str = "10.00",
    stock: int = 0,
    borrado: bool = False,
) -> Repuesto:
    repuesto = Repuesto(
        codigo=codigo,
        descripcion=descripcion,
        precio=Decimal(precio),
        stock=stock,
        borrado_en=datetime.now(timezone.utc) if borrado else None,
    )
    return await sesion.agregar_y_refrescar(repuesto)


@pytest.mark.asyncio
async def test_listado_excluye_borrados_y_ordena_por_codigo(sesion: SesionFalsa):
    await sembrar(sesion, "R-002", "Bujía")
    await sembrar(sesion, "R-001", "Filtro de aceite")
    await sembrar(sesion, "R-003", "Pastillas", borrado=True)
    sesion.confirmar_siembra()

    repo = RepuestoRepository(sesion)
    filas = await repo.listar_paginado(q=None, offset=0, limit=10)

    assert [f.codigo for f in filas] == ["R-001", "R-002"]
    assert await repo.contar_vigentes(q=None) == 2


@pytest.mark.asyncio
async def test_listado_filtra_por_descripcion(sesion: SesionFalsa):
    await sembrar(sesion, "R-001", "Filtro de aceite")
    await sembrar(sesion, "R-002", "Bujía de encendido")
    sesion.confirmar_siembra()

    repo = RepuestoRepository(sesion)
    filas = await repo.listar_paginado(q="FILTRO", offset=0, limit=10)

    assert [f.codigo for f in filas] == ["R-001"]
    assert await repo.contar_vigentes(q="bujía") == 1


@pytest.mark.asyncio
async def test_get_by_codigo_vigente_ignora_borrados(sesion: SesionFalsa):
    await sembrar(sesion, "R-001", "Filtro", borrado=True)
    sesion.confirmar_siembra()

    repo = RepuestoRepository(sesion)
    assert await repo.get_by_codigo_vigente("R-001") is None


@pytest.mark.asyncio
async def test_get_para_actualizar_devuelve_vigente(sesion: SesionFalsa):
    repuesto = await sembrar(sesion, "R-001", "Filtro")
    sesion.confirmar_siembra()

    repo = RepuestoRepository(sesion)
    encontrado = await repo.get_para_actualizar(repuesto.id)

    assert encontrado is not None
    assert encontrado.codigo == "R-001"


@pytest.mark.asyncio
async def test_repositorios_de_historial_bloquean_update_y_delete(sesion: SesionFalsa):
    movimientos = MovimientoStockRepository(sesion)
    precios = HistorialPrecioRepuestoRepository(sesion)

    with pytest.raises(NotImplementedError):
        await movimientos.update(MovimientoStock(repuesto_id=1, usuario_id=1, cantidad=1, motivo="X"))
    with pytest.raises(NotImplementedError):
        await movimientos.delete(MovimientoStock(repuesto_id=1, usuario_id=1, cantidad=1, motivo="X"))
    with pytest.raises(NotImplementedError):
        await precios.update(
            HistorialPrecioRepuesto(
                repuesto_id=1,
                usuario_id=1,
                precio_anterior=Decimal("1.00"),
                precio_nuevo=Decimal("2.00"),
            )
        )
    with pytest.raises(NotImplementedError):
        await precios.delete(
            HistorialPrecioRepuesto(
                repuesto_id=1,
                usuario_id=1,
                precio_anterior=Decimal("1.00"),
                precio_nuevo=Decimal("2.00"),
            )
        )
