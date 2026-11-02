"""Pruebas del `CatalogoService` con lógica REAL sobre SQLite en memoria.

Transparencia obligatoria (no afirmar falsamente "end-to-end"):

- Se ejecutan los servicios REALES (`CatalogoService.*`), los repositorios REALES
  y el Unit of Work REAL; ningún método del servicio está mockeado.
- La base NO es PostgreSQL: es SQLite (driver stdlib `sqlite3`) en memoria.
- QUÉ NO CUBRE (requiere PostgreSQL real, ver C-09):
  * el bloqueo `SELECT ... FOR UPDATE` (SQLite lo ignora silenciosamente);
  * el índice único PARCIAL `uq_repuesto_codigo_activo` (se elimina en la base
    simulada porque SQLite lo crea completo, más estricto que producción);
  * los triggers PL/pgSQL de sólo agregado (`test/solo_agregado.sql`).

Configuración de entorno: no se necesita bcrypt ni JWT en este módulo, pero el
fixture autouse mantiene el mismo patrón que el resto de la suite.
"""

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core.auth import UsuarioActual
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.repuestos.schemas import (
    ReponerStockRequest,
    RepuestoCreate,
    RepuestoUpdate,
)
from app.modules.repuestos.service import CatalogoService
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork
from test.infra_sqlite import SesionFalsa, esquema_sqlite


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_repuestos_servicio_1234567890")


@pytest.fixture
async def sesion():
    gen = esquema_sqlite()
    base: SesionFalsa = next(gen)
    try:
        yield base
    finally:
        gen.close()


def actor_admin(usuario_id: int = 1) -> UsuarioActual:
    return UsuarioActual(
        id=usuario_id,
        email="admin@test.com",
        nombre="Administrador",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
        roles_token=["ADMIN"],
    )


async def sembrar_repuesto(
    sesion: SesionFalsa,
    codigo: str = "R-001",
    descripcion: str = "Filtro de aceite",
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


# -------------------------------------------------------------
# 2.1 — listar y obtener
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_listar_excluye_borrados_y_pagina(sesion: SesionFalsa):
    await sembrar_repuesto(sesion, "R-001", "Filtro de aceite")
    await sembrar_repuesto(sesion, "R-002", "Bujía")
    await sembrar_repuesto(sesion, "R-003", "Pastillas", borrado=True)
    sesion.confirmar_siembra()

    pagina = await CatalogoService.listar(None, 1, 1, RepuestosUnitOfWork(sesion))

    assert pagina.total == 2
    assert pagina.pages == 2
    assert pagina.page == 1
    assert pagina.size == 1
    assert [item.codigo for item in pagina.items] == ["R-001"]


@pytest.mark.asyncio
async def test_listar_busca_por_descripcion(sesion: SesionFalsa):
    await sembrar_repuesto(sesion, "R-001", "Filtro de aceite")
    await sembrar_repuesto(sesion, "R-002", "Bujía de encendido")
    sesion.confirmar_siembra()

    pagina = await CatalogoService.listar("bujía", 1, 20, RepuestosUnitOfWork(sesion))

    assert pagina.total == 1
    assert pagina.items[0].codigo == "R-002"


@pytest.mark.asyncio
async def test_listar_pagina_fuera_de_rango_responde_422(sesion: SesionFalsa):
    await sembrar_repuesto(sesion, "R-001", "Filtro")
    sesion.confirmar_siembra()

    with pytest.raises(HTTPException) as exc_info:
        await CatalogoService.listar(None, 5, 20, RepuestosUnitOfWork(sesion))

    assert exc_info.value.status_code == 422
    assert "Página fuera de rango" in exc_info.value.detail


@pytest.mark.asyncio
async def test_obtener_existente_devuelve_dto(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro", precio="10.50", stock=3)
    sesion.confirmar_siembra()

    dto = await CatalogoService.obtener(repuesto.id, RepuestosUnitOfWork(sesion))

    assert dto.id == repuesto.id
    assert dto.codigo == "R-001"
    assert dto.precio == Decimal("10.50")
    assert dto.stock == 3


@pytest.mark.asyncio
async def test_obtener_inexistente_o_borrado_responde_404(sesion: SesionFalsa):
    borrado = await sembrar_repuesto(sesion, "R-002", "Bujía", borrado=True)
    sesion.confirmar_siembra()

    for id in (9999, borrado.id):
        with pytest.raises(HTTPException) as exc_info:
            await CatalogoService.obtener(id, RepuestosUnitOfWork(sesion))
        assert exc_info.value.status_code == 404
        assert "Repuesto no encontrado" in exc_info.value.detail


# -------------------------------------------------------------
# 2.2 — crear
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_crear_con_stock_inicial_registra_movimiento_alta(sesion: SesionFalsa):
    dto = await CatalogoService.crear(
        RepuestoCreate(
            codigo="R-100",
            descripcion="Filtro de aire",
            precio="25.00",
            stock_inicial=4,
        ),
        actor_admin(7),
        RepuestosUnitOfWork(sesion),
    )

    assert dto.id is not None
    assert dto.stock == 4
    assert dto.precio == Decimal("25.00")
    assert sesion.contar(Repuesto) == 1

    movimientos = sesion.listar(MovimientoStock)
    assert len(movimientos) == 1
    assert movimientos[0].repuesto_id == dto.id
    assert movimientos[0].usuario_id == 7
    assert movimientos[0].cantidad == 4
    assert movimientos[0].motivo == "ALTA"
    assert movimientos[0].orden_id is None
    assert sesion.contador_commits == 1


@pytest.mark.asyncio
async def test_crear_sin_stock_inicial_no_registra_movimiento(sesion: SesionFalsa):
    dto = await CatalogoService.crear(
        RepuestoCreate(codigo="R-101", descripcion="Bujía", precio="8.00"),
        actor_admin(),
        RepuestosUnitOfWork(sesion),
    )

    assert dto.stock == 0
    assert sesion.contar(MovimientoStock) == 0


@pytest.mark.asyncio
async def test_crear_codigo_duplicado_vigente_responde_409(sesion: SesionFalsa):
    await sembrar_repuesto(sesion, "R-100", "Filtro")
    sesion.confirmar_siembra()

    commits_antes = sesion.contador_commits
    with pytest.raises(HTTPException) as exc_info:
        await CatalogoService.crear(
            RepuestoCreate(codigo="R-100", descripcion="Otro filtro", precio="9.00"),
            actor_admin(),
            RepuestosUnitOfWork(sesion),
        )

    assert exc_info.value.status_code == 409
    assert "código de repuesto ya se encuentra registrado" in exc_info.value.detail
    assert sesion.contar(Repuesto) == 1
    assert sesion.contador_commits - commits_antes == 0


@pytest.mark.asyncio
async def test_crear_rollback_ante_fallo_de_insercion(sesion: SesionFalsa):
    """Si falla el movimiento de alta, el rollback descarta también el repuesto."""
    sesion.confirmar_siembra()
    with sesion.engine.begin() as conn:
        conn.execute(text(
            "CREATE TRIGGER trg_fallo_movimiento BEFORE INSERT ON movimiento_stock "
            "BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
        ))

    commits_antes = sesion.contador_commits
    with pytest.raises(Exception):
        await CatalogoService.crear(
            RepuestoCreate(
                codigo="R-500",
                descripcion="Repuesto con fallo",
                precio="10.00",
                stock_inicial=2,
            ),
            actor_admin(),
            RepuestosUnitOfWork(sesion),
        )

    assert sesion.contar(Repuesto) == 0
    assert sesion.contar(MovimientoStock) == 0
    assert sesion.contador_commits - commits_antes == 0


# -------------------------------------------------------------
# 2.3 — actualizar
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_actualizar_precio_genera_historial(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro", precio="10.00")
    sesion.confirmar_siembra()

    dto = await CatalogoService.actualizar(
        repuesto.id,
        RepuestoUpdate(precio="12.50"),
        actor_admin(9),
        RepuestosUnitOfWork(sesion),
    )

    assert dto.precio == Decimal("12.50")
    historial = sesion.listar(HistorialPrecioRepuesto)
    assert len(historial) == 1
    assert historial[0].repuesto_id == repuesto.id
    assert historial[0].usuario_id == 9
    assert historial[0].precio_anterior == Decimal("10.00")
    assert historial[0].precio_nuevo == Decimal("12.50")


@pytest.mark.asyncio
async def test_actualizar_precio_identico_no_genera_historial(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro", precio="10.00")
    sesion.confirmar_siembra()

    dto = await CatalogoService.actualizar(
        repuesto.id,
        RepuestoUpdate(precio="10.00"),
        actor_admin(),
        RepuestosUnitOfWork(sesion),
    )

    assert dto.precio == Decimal("10.00")
    assert sesion.contar(HistorialPrecioRepuesto) == 0


@pytest.mark.asyncio
async def test_actualizar_solo_descripcion_no_genera_historial(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro", precio="10.00")
    sesion.confirmar_siembra()

    dto = await CatalogoService.actualizar(
        repuesto.id,
        RepuestoUpdate(descripcion="Filtro de aceite premium"),
        actor_admin(),
        RepuestosUnitOfWork(sesion),
    )

    assert dto.descripcion == "Filtro de aceite premium"
    assert dto.precio == Decimal("10.00")
    assert sesion.contar(HistorialPrecioRepuesto) == 0


@pytest.mark.asyncio
async def test_actualizar_inexistente_responde_404(sesion: SesionFalsa):
    with pytest.raises(HTTPException) as exc_info:
        await CatalogoService.actualizar(
            9999,
            RepuestoUpdate(precio="11.00"),
            actor_admin(),
            RepuestosUnitOfWork(sesion),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_actualizar_rollback_del_historial_no_cambia_el_precio(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro", precio="10.00")
    sesion.confirmar_siembra()
    with sesion.engine.begin() as conn:
        conn.execute(text(
            "CREATE TRIGGER trg_fallo_historial BEFORE INSERT ON historial_precio_repuesto "
            "BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
        ))

    commits_antes = sesion.contador_commits
    with pytest.raises(Exception):
        await CatalogoService.actualizar(
            repuesto.id,
            RepuestoUpdate(precio="15.00"),
            actor_admin(),
            RepuestosUnitOfWork(sesion),
        )

    assert sesion.contar(HistorialPrecioRepuesto) == 0
    precio_persistido = sesion.listar(Repuesto)[0].precio
    assert precio_persistido == Decimal("10.00")
    assert sesion.contador_commits - commits_antes == 0


# -------------------------------------------------------------
# 2.4 — reponer
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_reponer_incrementa_stock_y_registra_movimiento(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro", stock=2)
    sesion.confirmar_siembra()

    dto = await CatalogoService.reponer(
        repuesto.id,
        ReponerStockRequest(cantidad=5),
        actor_admin(4),
        RepuestosUnitOfWork(sesion),
    )

    assert dto.stock == 7
    movimientos = sesion.listar(MovimientoStock)
    assert len(movimientos) == 1
    assert movimientos[0].cantidad == 5
    assert movimientos[0].motivo == "REPOSICION"
    assert movimientos[0].usuario_id == 4


@pytest.mark.asyncio
async def test_reponer_inexistente_responde_404(sesion: SesionFalsa):
    with pytest.raises(HTTPException) as exc_info:
        await CatalogoService.reponer(
            9999,
            ReponerStockRequest(cantidad=1),
            actor_admin(),
            RepuestosUnitOfWork(sesion),
        )

    assert exc_info.value.status_code == 404
    assert sesion.contar(MovimientoStock) == 0


@pytest.mark.asyncio
async def test_reponer_rollback_del_incremento(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro", stock=2)
    sesion.confirmar_siembra()
    with sesion.engine.begin() as conn:
        conn.execute(text(
            "CREATE TRIGGER trg_fallo_movimiento BEFORE INSERT ON movimiento_stock "
            "BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
        ))

    with pytest.raises(Exception):
        await CatalogoService.reponer(
            repuesto.id,
            ReponerStockRequest(cantidad=5),
            actor_admin(),
            RepuestosUnitOfWork(sesion),
        )

    assert sesion.listar(Repuesto)[0].stock == 2
    assert sesion.contar(MovimientoStock) == 0


# -------------------------------------------------------------
# 2.5 — dar de baja
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_dar_de_baja_oculta_en_listado_y_detalle(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro")
    sesion.confirmar_siembra()

    await CatalogoService.dar_de_baja(repuesto.id, RepuestosUnitOfWork(sesion))

    assert sesion.listar(Repuesto)[0].borrado_en is not None
    assert sesion.contar(Repuesto) == 1  # borrado lógico: la fila sigue existiendo

    pagina = await CatalogoService.listar(None, 1, 20, RepuestosUnitOfWork(sesion))
    assert pagina.total == 0

    with pytest.raises(HTTPException) as exc_info:
        await CatalogoService.obtener(repuesto.id, RepuestosUnitOfWork(sesion))
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_dar_de_baja_inexistente_o_repetida_responde_404(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro")
    sesion.confirmar_siembra()
    await CatalogoService.dar_de_baja(repuesto.id, RepuestosUnitOfWork(sesion))

    for id in (repuesto.id, 9999):
        with pytest.raises(HTTPException) as exc_info:
            await CatalogoService.dar_de_baja(id, RepuestosUnitOfWork(sesion))
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_codigo_se_libera_tras_la_baja(sesion: SesionFalsa):
    original = await sembrar_repuesto(sesion, "R-001", "Filtro viejo")
    sesion.confirmar_siembra()
    await CatalogoService.dar_de_baja(original.id, RepuestosUnitOfWork(sesion))

    dto = await CatalogoService.crear(
        RepuestoCreate(codigo="R-001", descripcion="Filtro nuevo", precio="12.00"),
        actor_admin(),
        RepuestosUnitOfWork(sesion),
    )

    assert dto.id != original.id
    assert dto.codigo == "R-001"
    assert sesion.contar(Repuesto) == 2


# -------------------------------------------------------------
# 2.6 — historiales paginados
# -------------------------------------------------------------

async def _cargar_movimientos(sesion: SesionFalsa, repuesto_id: int) -> None:
    ahora = datetime.now(timezone.utc)
    for indice in range(3):
        await sesion.agregar_y_refrescar(
            MovimientoStock(
                repuesto_id=repuesto_id,
                usuario_id=1,
                cantidad=indice + 1,
                motivo="REPOSICION",
                cuando=ahora + timedelta(minutes=indice),
            )
        )


@pytest.mark.asyncio
async def test_listar_movimientos_pagina_y_ordena_desc(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro")
    await _cargar_movimientos(sesion, repuesto.id)
    sesion.confirmar_siembra()

    pagina = await CatalogoService.listar_movimientos(
        repuesto.id, 1, 2, RepuestosUnitOfWork(sesion)
    )

    assert pagina.total == 3
    assert pagina.pages == 2
    assert [m.cantidad for m in pagina.items] == [3, 2]


@pytest.mark.asyncio
async def test_listar_precios_pagina_y_ordena_desc(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro", precio="10.00")
    ahora = datetime.now(timezone.utc)
    for indice, precio in enumerate(("11.00", "12.00", "13.00")):
        await sesion.agregar_y_refrescar(
            HistorialPrecioRepuesto(
                repuesto_id=repuesto.id,
                usuario_id=1,
                precio_anterior=Decimal("10.00") if indice == 0 else Decimal(precio) - 1,
                precio_nuevo=Decimal(precio),
                cuando=ahora + timedelta(minutes=indice),
            )
        )
    sesion.confirmar_siembra()

    pagina = await CatalogoService.listar_precios(
        repuesto.id, 1, 2, RepuestosUnitOfWork(sesion)
    )

    assert pagina.total == 3
    assert [p.precio_nuevo for p in pagina.items] == [Decimal("13.00"), Decimal("12.00")]


@pytest.mark.asyncio
async def test_historiales_vacios_devuelven_total_cero(sesion: SesionFalsa):
    repuesto = await sembrar_repuesto(sesion, "R-001", "Filtro")
    sesion.confirmar_siembra()

    movimientos = await CatalogoService.listar_movimientos(
        repuesto.id, 1, 20, RepuestosUnitOfWork(sesion)
    )
    precios = await CatalogoService.listar_precios(
        repuesto.id, 1, 20, RepuestosUnitOfWork(sesion)
    )

    assert movimientos.total == 0
    assert movimientos.items == []
    assert movimientos.pages == 1
    assert precios.total == 0
    assert precios.items == []


@pytest.mark.asyncio
async def test_historiales_de_repuesto_inexistente_responden_404(sesion: SesionFalsa):
    borrado = await sembrar_repuesto(sesion, "R-002", "Bujía", borrado=True)
    sesion.confirmar_siembra()

    for id in (9999, borrado.id):
        with pytest.raises(HTTPException) as exc_info:
            await CatalogoService.listar_movimientos(id, 1, 20, RepuestosUnitOfWork(sesion))
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            await CatalogoService.listar_precios(id, 1, 20, RepuestosUnitOfWork(sesion))
        assert exc_info.value.status_code == 404
