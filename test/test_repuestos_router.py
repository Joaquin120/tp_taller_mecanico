"""Pruebas del router de repuestos con la app REAL y SQLite en memoria.

Transparencia obligatoria (no afirmar falsamente "end-to-end"):

- Se ejecuta la app REAL de FastAPI (router, dependencias, servicios, repositorios
  y Unit of Work) sobre SQLite (driver stdlib `sqlite3`) en memoria, con bcrypt real
  para el `dummy_hash` de la app. NO se mockea `CatalogoService` ni los repositorios.
- `get_current_user` se sustituye por un `UsuarioActual` sintético para aislar el
  objeto de estas pruebas (contrato, RBAC y códigos HTTP del módulo). El flujo real
  de cookie/JWT ya está cubierto por `test_c05_integracion.py` y el módulo de auth.
- QUÉ NO CUBRE (requiere PostgreSQL real, ver C-09):
  * el índice único PARCIAL `uq_repuesto_codigo_activo` (se elimina en la base
    simulada porque SQLite lo crea completo, más estricto que producción);
  * los triggers PL/pgSQL de sólo agregado (`test/solo_agregado.sql`);
  * la concurrencia real del índice parcial y `SELECT ... FOR UPDATE`.
"""

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from app.core.auth import UsuarioActual, get_current_user
from app.core.security import hash_password
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from test.infra_sqlite import SesionFalsa, esquema_sqlite, instalar_en_app
from main import app


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_repuestos_router_1234567890")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")


@pytest.fixture
async def sesion():
    gen = esquema_sqlite()
    base: SesionFalsa = next(gen)
    try:
        yield base
    finally:
        gen.close()


@pytest.fixture
async def base_instalada(sesion: SesionFalsa):
    dummy_hash = await hash_password("dummy_hash_solo_para_pruebas")
    with instalar_en_app(app, sesion, dummy_hash):
        yield sesion


@pytest.fixture
def actor():
    """Instala un `UsuarioActual` sintético y limpia el override al terminar."""
    instalado: list[UsuarioActual] = []

    def _instalar(roles: list[str], usuario_id: int = 1) -> UsuarioActual:
        usuario = UsuarioActual(
            id=usuario_id,
            email=f"user_{usuario_id}@test.com",
            nombre="Usuario de prueba",
            activo=True,
            debe_cambiar_password=False,
            roles=list(roles),
            roles_token=list(roles),
        )
        app.dependency_overrides[get_current_user] = lambda: usuario
        instalado.append(usuario)
        return usuario

    yield _instalar
    app.dependency_overrides.pop(get_current_user, None)


def cliente_http() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


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
    repuesto = await sesion.agregar_y_refrescar(repuesto)
    sesion.confirmar_siembra()
    return repuesto


# -------------------------------------------------------------
# 3.1 — Endpoints y códigos de respuesta
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_listar_repuestos_200_para_recepcion(base_instalada: SesionFalsa, actor):
    await sembrar_repuesto(base_instalada, "R-001", "Filtro")
    await sembrar_repuesto(base_instalada, "R-002", "Bujía")
    actor(["RECEPCION"], usuario_id=2)

    async with cliente_http() as client:
        response = await client.get("/repuestos")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert [item["codigo"] for item in data["items"]] == ["R-001", "R-002"]


@pytest.mark.asyncio
async def test_listar_repuestos_404_no_aplica_pero_pagina_invalida_es_422(
    base_instalada: SesionFalsa, actor
):
    await sembrar_repuesto(base_instalada)
    actor(["ADMIN"])

    async with cliente_http() as client:
        response = await client.get("/repuestos", params={"page": 9, "size": 1})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_obtener_repuesto_200_para_mecanico(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada, "R-001", "Filtro", stock=4)
    actor(["MECANICO"], usuario_id=3)

    async with cliente_http() as client:
        response = await client.get(f"/repuestos/{repuesto.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["codigo"] == "R-001"
    assert data["stock"] == 4
    assert Decimal(str(data["precio"])) == Decimal("10.00")


@pytest.mark.asyncio
async def test_obtener_repuesto_inexistente_404(base_instalada: SesionFalsa, actor):
    actor(["ADMIN"])

    async with cliente_http() as client:
        response = await client.get("/repuestos/9999")

    assert response.status_code == 404
    assert "Repuesto no encontrado" in response.json()["detail"]


@pytest.mark.asyncio
async def test_crear_repuesto_201_con_stock_inicial(base_instalada: SesionFalsa, actor):
    actor(["ADMIN"], usuario_id=7)

    async with cliente_http() as client:
        response = await client.post(
            "/repuestos",
            json={
                "codigo": "R-100",
                "descripcion": "Filtro de aire",
                "precio": "25.00",
                "stock_inicial": 4,
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["codigo"] == "R-100"
    assert data["stock"] == 4

    movimientos = base_instalada.listar(MovimientoStock)
    assert len(movimientos) == 1
    assert movimientos[0].motivo == "ALTA"
    assert movimientos[0].usuario_id == 7


@pytest.mark.asyncio
async def test_crear_repuesto_codigo_duplicado_409(base_instalada: SesionFalsa, actor):
    await sembrar_repuesto(base_instalada, "R-100")
    actor(["ADMIN"])

    async with cliente_http() as client:
        response = await client.post(
            "/repuestos",
            json={"codigo": "R-100", "descripcion": "Otro", "precio": "9.00"},
        )

    assert response.status_code == 409
    assert "ya se encuentra registrado" in response.json()["detail"]


@pytest.mark.asyncio
async def test_crear_repuesto_precio_invalido_422(base_instalada: SesionFalsa, actor):
    actor(["ADMIN"])

    async with cliente_http() as client:
        response = await client.post(
            "/repuestos",
            json={"codigo": "R-101", "descripcion": "Filtro", "precio": "0"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_actualizar_precio_200_y_registra_historial(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada, precio="10.00")
    actor(["ADMIN"], usuario_id=5)

    async with cliente_http() as client:
        response = await client.patch(
            f"/repuestos/{repuesto.id}",
            json={"precio": "12.50"},
        )
        historial = await client.get(f"/repuestos/{repuesto.id}/precios")

    assert response.status_code == 200
    assert Decimal(str(response.json()["precio"])) == Decimal("12.50")
    assert historial.status_code == 200
    assert historial.json()["total"] == 1
    assert base_instalada.contar(HistorialPrecioRepuesto) == 1


@pytest.mark.asyncio
async def test_actualizar_repuesto_inexistente_404(base_instalada: SesionFalsa, actor):
    actor(["ADMIN"])

    async with cliente_http() as client:
        response = await client.patch("/repuestos/9999", json={"precio": "12.00"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_actualizar_sin_campos_422(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada)
    actor(["ADMIN"])

    async with cliente_http() as client:
        response = await client.patch(f"/repuestos/{repuesto.id}", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_eliminar_repuesto_204_y_luego_404(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada)
    actor(["ADMIN"])

    async with cliente_http() as client:
        primera = await client.delete(f"/repuestos/{repuesto.id}")
        segunda = await client.delete(f"/repuestos/{repuesto.id}")
        detalle = await client.get(f"/repuestos/{repuesto.id}")

    assert primera.status_code == 204
    assert segunda.status_code == 404
    assert detalle.status_code == 404


@pytest.mark.asyncio
async def test_reponer_stock_200_y_movimiento(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada, stock=2)
    actor(["ADMIN"], usuario_id=8)

    async with cliente_http() as client:
        response = await client.post(
            f"/repuestos/{repuesto.id}/reponer",
            json={"cantidad": 5},
        )
        movimientos = await client.get(f"/repuestos/{repuesto.id}/movimientos")

    assert response.status_code == 200
    assert response.json()["stock"] == 7
    assert movimientos.status_code == 200
    assert movimientos.json()["total"] == 1
    assert movimientos.json()["items"][0]["motivo"] == "REPOSICION"
    assert movimientos.json()["items"][0]["usuario_id"] == 8


@pytest.mark.asyncio
async def test_reponer_cantidad_invalida_422(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada, stock=2)
    actor(["ADMIN"])

    async with cliente_http() as client:
        response = await client.post(
            f"/repuestos/{repuesto.id}/reponer",
            json={"cantidad": 0},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_historiales_200_con_listado_vacio(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada)
    actor(["ADMIN"])

    async with cliente_http() as client:
        movimientos = await client.get(f"/repuestos/{repuesto.id}/movimientos")
        precios = await client.get(f"/repuestos/{repuesto.id}/precios")

    assert movimientos.status_code == 200
    assert movimientos.json()["total"] == 0
    assert precios.status_code == 200
    assert precios.json()["total"] == 0


# -------------------------------------------------------------
# 3.2 — Mapeo de errores de integridad sin filtrar PostgreSQL
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_violacion_de_unicidad_no_filtra_sql(
    base_instalada: SesionFalsa, actor, monkeypatch: pytest.MonkeyPatch
):
    """Una `IntegrityError` de unicidad se traduce a 409 con mensaje propio."""
    actor(["ADMIN"])

    async def _falla(*args, **kwargs):
        from unittest.mock import MagicMock

        orig = MagicMock()
        orig.constraint_name = "uq_repuesto_codigo_activo"
        orig.sqlstate = "23505"
        orig.pgcode = "23505"
        raise IntegrityError(
            "INSERT INTO repuesto (codigo) VALUES ('R-001')",
            ("R-001",),
            orig,
        )

    monkeypatch.setattr(
        "app.modules.repuestos.service.CatalogoService.crear",
        staticmethod(_falla),
    )

    async with cliente_http() as client:
        response = await client.post(
            "/repuestos",
            json={"codigo": "R-001", "descripcion": "Filtro", "precio": "10.00"},
        )

    assert response.status_code == 409
    body = response.text
    assert "código de repuesto ya se encuentra registrado" in body
    assert "INSERT INTO" not in body
    assert "repuesto" not in body.replace("código de repuesto", "")


# -------------------------------------------------------------
# 3.3 — Autorización
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_sin_sesion_responde_401(base_instalada: SesionFalsa):
    async with cliente_http() as client:
        response = await client.get("/repuestos")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cliente_no_puede_leer_repuestos_403(base_instalada: SesionFalsa, actor):
    actor(["CLIENTE"], usuario_id=10)

    async with cliente_http() as client:
        listado = await client.get("/repuestos")
        detalle = await client.get("/repuestos/1")

    assert listado.status_code == 403
    assert detalle.status_code == 403


@pytest.mark.asyncio
async def test_recepcion_no_puede_mutar_repuestos_403(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada)
    actor(["RECEPCION"], usuario_id=11)

    async with cliente_http() as client:
        alta = await client.post(
            "/repuestos",
            json={"codigo": "R-200", "descripcion": "Filtro", "precio": "10.00"},
        )
        patch = await client.patch(f"/repuestos/{repuesto.id}", json={"precio": "11.00"})
        baja = await client.delete(f"/repuestos/{repuesto.id}")
        reposicion = await client.post(
            f"/repuestos/{repuesto.id}/reponer", json={"cantidad": 1}
        )
        movimientos = await client.get(f"/repuestos/{repuesto.id}/movimientos")
        precios = await client.get(f"/repuestos/{repuesto.id}/precios")

    assert alta.status_code == 403
    assert patch.status_code == 403
    assert baja.status_code == 403
    assert reposicion.status_code == 403
    assert movimientos.status_code == 403
    assert precios.status_code == 403


@pytest.mark.asyncio
async def test_mecanico_no_puede_mutar_repuestos_403(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada)
    actor(["MECANICO"], usuario_id=12)

    async with cliente_http() as client:
        patch = await client.patch(f"/repuestos/{repuesto.id}", json={"precio": "11.00"})
        baja = await client.delete(f"/repuestos/{repuesto.id}")

    assert patch.status_code == 403
    assert baja.status_code == 403


# -------------------------------------------------------------
# 3.4 — El stock no viaja por PATCH y los historiales son de sólo lectura
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_con_stock_en_el_body_responde_422(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada, stock=3)
    actor(["ADMIN"])

    async with cliente_http() as client:
        response = await client.patch(
            f"/repuestos/{repuesto.id}",
            json={"precio": "11.00", "stock": 99},
        )

    assert response.status_code == 422
    assert base_instalada.listar(Repuesto)[0].stock == 3


@pytest.mark.asyncio
async def test_escrituras_sobre_historiales_responden_405(base_instalada: SesionFalsa, actor):
    repuesto = await sembrar_repuesto(base_instalada)
    actor(["ADMIN"])

    async with cliente_http() as client:
        post_movimientos = await client.post(
            f"/repuestos/{repuesto.id}/movimientos", json={"cantidad": 1}
        )
        delete_movimientos = await client.delete(f"/repuestos/{repuesto.id}/movimientos")
        post_precios = await client.post(
            f"/repuestos/{repuesto.id}/precios", json={"precio": "11.00"}
        )
        put_precios = await client.put(
            f"/repuestos/{repuesto.id}/precios", json={"precio": "11.00"}
        )

    assert post_movimientos.status_code == 405
    assert delete_movimientos.status_code == 405
    assert post_precios.status_code == 405
    assert put_precios.status_code == 405
