"""Pruebas de endpoints del ciclo de vida de las órdenes (router y RBAC)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

from app.modules.ordenes.models import OrdenTrabajo
from app.modules.repuestos.models import MovimientoStock
from main import app
from test.infra_sqlite import SesionFalsa, esquema_sqlite
from test.ordenes_fixtures import (
    actor_admin,
    actor_cliente,
    actor_mecanico,
    actor_recepcion,
    con_overrides,
    sembrar_escenario,
    sembrar_orden,
)


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_for_ordenes_router_123")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    app.state.dummy_hash = (
        "$2b$04$dummyhashfordefensetimingtestingonly1234567890123456789012"
    )
    mock_sf = MagicMock()
    mock_sf.return_value.__aenter__.return_value = AsyncMock()
    app.state.session_factory = mock_sf


@pytest.fixture
async def sesion():
    generador = esquema_sqlite()
    base: SesionFalsa = next(generador)
    try:
        yield base
    finally:
        generador.close()


def _cliente() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _crear_pendiente(sesion: SesionFalsa, datos, **kwargs) -> OrdenTrabajo:
    return await sembrar_orden(
        sesion,
        datos["vehiculo"].id,
        datos["recepcion"].id,
        estado=kwargs.pop("estado", "PENDIENTE"),
        items=kwargs.pop("items", [(datos["repuesto_1"], 1)]),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# GET /estados-orden
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_listar_estados_200_para_cualquier_autenticado(sesion: SesionFalsa):
    await sembrar_escenario(sesion)

    with con_overrides(sesion, actor_cliente(4)):
        async with _cliente() as client:
            response = await client.get("/estados-orden")

    assert response.status_code == 200
    assert [estado["codigo"] for estado in response.json()] == [
        "PENDIENTE",
        "EN_REPARACION",
        "TERMINADA",
        "CANCELADA",
    ]
    assert set(response.json()[0]) == {"codigo", "descripcion", "posicion", "es_final"}


@pytest.mark.asyncio
async def test_estados_orden_no_admite_metodos_de_escritura(sesion: SesionFalsa):
    await sembrar_escenario(sesion)

    with con_overrides(sesion, actor_admin(1)):
        async with _cliente() as client:
            response = await client.post("/estados-orden", json={"codigo": "X"})

    assert response.status_code == 405


# --------------------------------------------------------------------------- #
# POST /ordenes
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_crear_orden_201_con_recepcion(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)

    with con_overrides(sesion, actor_recepcion(datos["recepcion"].id)):
        async with _cliente() as client:
            response = await client.post(
                "/ordenes",
                json={
                    "vehiculo_id": datos["vehiculo"].id,
                    "falla": "Ruido en el motor",
                    "items": [{"repuesto_id": datos["repuesto_2"].id, "cantidad": 2}],
                },
            )

    assert response.status_code == 201
    cuerpo = response.json()
    assert cuerpo["estado"] == "PENDIENTE"
    assert cuerpo["total"] == "500.00"
    assert cuerpo["patente"] == "AA123BB"
    assert cuerpo["cliente"] == "Laura Gómez"
    assert [item["codigo"] for item in cuerpo["items"]] == ["REP-002"]
    assert cuerpo["historial"][0]["hasta_estado"] == "PENDIENTE"
    # No se filtra información interna.
    for prohibido in ("password_hash", "estado_rel", "vehiculo_id"):
        assert prohibido not in cuerpo


@pytest.mark.asyncio
async def test_crear_orden_403_para_mecanico_y_cliente(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)
    payload = {
        "vehiculo_id": datos["vehiculo"].id,
        "falla": "Falla",
        "items": [{"repuesto_id": datos["repuesto_1"].id, "cantidad": 1}],
    }

    for actor in (actor_mecanico(3), actor_cliente(4)):
        with con_overrides(sesion, actor):
            async with _cliente() as client:
                response = await client.post("/ordenes", json=payload)
        assert response.status_code == 403

    assert sesion.contar(OrdenTrabajo) == 0


@pytest.mark.asyncio
async def test_crear_orden_422_con_campos_extra(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)

    with con_overrides(sesion, actor_recepcion(datos["recepcion"].id)):
        async with _cliente() as client:
            response = await client.post(
                "/ordenes",
                json={
                    "vehiculo_id": datos["vehiculo"].id,
                    "falla": "Falla",
                    "total": "0.00",
                    "items": [{"repuesto_id": datos["repuesto_1"].id, "cantidad": 1}],
                },
            )

    assert response.status_code == 422
    assert sesion.contar(OrdenTrabajo) == 0


@pytest.mark.asyncio
async def test_crear_orden_422_sin_items(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)

    with con_overrides(sesion, actor_recepcion(datos["recepcion"].id)):
        async with _cliente() as client:
            response = await client.post(
                "/ordenes",
                json={
                    "vehiculo_id": datos["vehiculo"].id,
                    "falla": "Falla",
                    "items": [],
                },
            )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_crear_orden_409_con_vehiculo_inexistente(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)

    with con_overrides(sesion, actor_admin(datos["admin"].id)):
        async with _cliente() as client:
            response = await client.post(
                "/ordenes",
                json={
                    "vehiculo_id": 9999,
                    "falla": "Falla",
                    "items": [{"repuesto_id": datos["repuesto_1"].id, "cantidad": 1}],
                },
            )

    assert response.status_code == 409


# --------------------------------------------------------------------------- #
# GET /ordenes y /mis-ordenes
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_listar_ordenes_200_para_personal_y_403_para_cliente(
    sesion: SesionFalsa,
):
    datos = await sembrar_escenario(sesion)
    orden = await _crear_pendiente(sesion, datos)

    with con_overrides(sesion, actor_mecanico(datos["mecanico"].id)):
        async with _cliente() as client:
            response = await client.get("/ordenes", params={"estado": "PENDIENTE"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == orden.id

    with con_overrides(sesion, actor_cliente(datos["cliente_user"].id)):
        async with _cliente() as client:
            response = await client.get("/ordenes")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_listar_ordenes_422_con_estado_o_pagina_invalidos(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)
    await _crear_pendiente(sesion, datos)

    with con_overrides(sesion, actor_admin(datos["admin"].id)):
        async with _cliente() as client:
            estado_invalido = await client.get("/ordenes", params={"estado": "ROTA"})
            pagina_fuera = await client.get("/ordenes", params={"page": 99})

    assert estado_invalido.status_code == 422
    assert pagina_fuera.status_code == 422


@pytest.mark.asyncio
async def test_mis_ordenes_filtra_por_el_cliente_autenticado(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)
    propia = await _crear_pendiente(sesion, datos)
    await sembrar_orden(
        sesion, datos["vehiculo_ajeno"].id, datos["recepcion"].id, estado="PENDIENTE"
    )

    with con_overrides(sesion, actor_cliente(datos["cliente_user"].id)):
        async with _cliente() as client:
            response = await client.get("/mis-ordenes")

    assert response.status_code == 200
    assert [orden["id"] for orden in response.json()["items"]] == [propia.id]


# --------------------------------------------------------------------------- #
# GET /ordenes/{id}
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_detalle_200_para_el_duenio_403_para_terceros_y_404_si_no_existe(
    sesion: SesionFalsa,
):
    datos = await sembrar_escenario(sesion)
    orden = await _crear_pendiente(sesion, datos)

    with con_overrides(sesion, actor_cliente(datos["cliente_user"].id)):
        async with _cliente() as client:
            propio = await client.get(f"/ordenes/{orden.id}")

    assert propio.status_code == 200
    assert propio.json()["total"] == "100.00"
    assert propio.json()["items"][0]["codigo"] == "REP-001"

    with con_overrides(sesion, actor_cliente(999)):
        async with _cliente() as client:
            ajeno = await client.get(f"/ordenes/{orden.id}")

    assert ajeno.status_code == 403

    with con_overrides(sesion, actor_admin(datos["admin"].id)):
        async with _cliente() as client:
            inexistente = await client.get("/ordenes/9999")

    assert inexistente.status_code == 404


# --------------------------------------------------------------------------- #
# POST /ordenes/{id}/iniciar
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_iniciar_orden_200_para_mecanico_y_403_para_recepcion(
    sesion: SesionFalsa,
):
    datos = await sembrar_escenario(sesion)
    orden = await _crear_pendiente(sesion, datos)

    with con_overrides(sesion, actor_recepcion(datos["recepcion"].id)):
        async with _cliente() as client:
            sin_permiso = await client.post(f"/ordenes/{orden.id}/iniciar")

    assert sin_permiso.status_code == 403

    with con_overrides(sesion, actor_mecanico(datos["mecanico"].id)):
        async with _cliente() as client:
            response = await client.post(f"/ordenes/{orden.id}/iniciar")

    assert response.status_code == 200
    assert response.json()["estado"] == "EN_REPARACION"
    assert response.json()["mecanico_id"] == datos["mecanico"].id


@pytest.mark.asyncio
async def test_iniciar_orden_409_si_ya_esta_en_reparacion(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)
    orden = await _crear_pendiente(sesion, datos, estado="EN_REPARACION")

    with con_overrides(sesion, actor_mecanico(datos["mecanico"].id)):
        async with _cliente() as client:
            response = await client.post(f"/ordenes/{orden.id}/iniciar")

    assert response.status_code == 409


# --------------------------------------------------------------------------- #
# POST /ordenes/{id}/terminar (RN-13 + BackgroundTasks)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_terminar_ordena_el_aviso_despues_del_commit(
    sesion: SesionFalsa, monkeypatch: pytest.MonkeyPatch
):
    datos = await sembrar_escenario(sesion)
    orden = await _crear_pendiente(
        sesion,
        datos,
        estado="EN_REPARACION",
        mecanico_id=datos["mecanico"].id,
        items=[(datos["repuesto_2"], 1)],
    )
    llamadas: list[tuple] = []

    async def _aviso_registrado(orden_id: int, destinatario: str) -> None:
        estado = await sesion.execute(
            select(OrdenTrabajo.estado).where(OrdenTrabajo.id == orden_id)
        )
        llamadas.append(
            (
                orden_id,
                destinatario,
                estado.scalar_one(),
                sesion.contar(MovimientoStock),
                sesion.contador_commits,
            )
        )

    monkeypatch.setattr(
        "app.modules.ordenes.router.avisar_cliente_simulado", _aviso_registrado
    )

    with con_overrides(sesion, actor_mecanico(datos["mecanico"].id)):
        async with _cliente() as client:
            response = await client.post(f"/ordenes/{orden.id}/terminar")

    assert response.status_code == 200
    assert response.json()["estado"] == "TERMINADA"
    # El aviso ve el commit ya confirmado: estado TERMINADA y movimiento persistido.
    assert llamadas == [(orden.id, "Laura Gómez", "TERMINADA", 1, 1)]


@pytest.mark.asyncio
async def test_terminar_sin_stock_409_y_sin_aviso(
    sesion: SesionFalsa, monkeypatch: pytest.MonkeyPatch
):
    datos = await sembrar_escenario(sesion)
    orden = await _crear_pendiente(
        sesion,
        datos,
        estado="EN_REPARACION",
        mecanico_id=datos["mecanico"].id,
        items=[(datos["repuesto_2"], 5)],
    )
    llamadas: list[tuple] = []

    async def _aviso_registrado(*args) -> None:  # pragma: no cover - no debe llamarse
        llamadas.append(args)

    monkeypatch.setattr(
        "app.modules.ordenes.router.avisar_cliente_simulado", _aviso_registrado
    )

    with con_overrides(sesion, actor_mecanico(datos["mecanico"].id)):
        async with _cliente() as client:
            response = await client.post(f"/ordenes/{orden.id}/terminar")

    assert response.status_code == 409
    assert "REP-002" in response.json()["detail"]
    assert llamadas == []
    assert sesion.contar(MovimientoStock) == 0
    assert sesion.contador_commits == 0


@pytest.mark.asyncio
async def test_terminar_403_para_mecanico_no_asignado(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)
    orden = await _crear_pendiente(
        sesion,
        datos,
        estado="EN_REPARACION",
        mecanico_id=datos["mecanico"].id,
    )

    with con_overrides(sesion, actor_mecanico(datos["otro_mecanico"].id)):
        async with _cliente() as client:
            response = await client.post(f"/ordenes/{orden.id}/terminar")

    assert response.status_code == 403
    assert sesion.contar(MovimientoStock) == 0


@pytest.mark.asyncio
async def test_terminar_404_si_la_orden_no_existe(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)

    with con_overrides(sesion, actor_admin(datos["admin"].id)):
        async with _cliente() as client:
            response = await client.post("/ordenes/9999/terminar")

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# POST /ordenes/{id}/cancelar (RN-12)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cancelar_200_para_el_duenio_y_409_tras_terminar(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)
    orden = await _crear_pendiente(sesion, datos)

    with con_overrides(sesion, actor_cliente(datos["cliente_user"].id)):
        async with _cliente() as client:
            response = await client.post(f"/ordenes/{orden.id}/cancelar")

    assert response.status_code == 200
    assert response.json()["estado"] == "CANCELADA"

    with con_overrides(sesion, actor_cliente(datos["cliente_user"].id)):
        async with _cliente() as client:
            repetida = await client.post(f"/ordenes/{orden.id}/cancelar")

    assert repetida.status_code == 409


@pytest.mark.asyncio
async def test_cancelar_403_para_mecanico(sesion: SesionFalsa):
    datos = await sembrar_escenario(sesion)
    orden = await _crear_pendiente(sesion, datos)

    with con_overrides(sesion, actor_mecanico(datos["mecanico"].id)):
        async with _cliente() as client:
            response = await client.post(f"/ordenes/{orden.id}/cancelar")

    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Autenticación y contrato de rutas
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metodo, ruta",
    [
        ("get", "/estados-orden"),
        ("post", "/ordenes"),
        ("get", "/ordenes"),
        ("get", "/mis-ordenes"),
        ("get", "/ordenes/1"),
        ("post", "/ordenes/1/iniciar"),
        ("post", "/ordenes/1/terminar"),
        ("post", "/ordenes/1/cancelar"),
    ],
)
async def test_endpoints_exigen_sesion(metodo: str, ruta: str):
    async with _cliente() as client:
        response = await getattr(client, metodo)(ruta)

    assert response.status_code == 401
    assert "cookie" in response.json()["detail"].lower()


def test_no_existen_rutas_de_historial() -> None:
    rutas = app.openapi()["paths"]

    assert not [ruta for ruta in rutas if "historial" in ruta]


def test_openapi_documenta_los_ocho_endpoints() -> None:
    rutas = app.openapi()["paths"]

    esperados = {
        ("/estados-orden", "get"),
        ("/ordenes", "post"),
        ("/ordenes", "get"),
        ("/mis-ordenes", "get"),
        ("/ordenes/{orden_id}", "get"),
        ("/ordenes/{orden_id}/iniciar", "post"),
        ("/ordenes/{orden_id}/terminar", "post"),
        ("/ordenes/{orden_id}/cancelar", "post"),
    }
    presentes = {
        (ruta, metodo)
        for ruta, operaciones in rutas.items()
        for metodo in operaciones
        if ruta.startswith(("/ordenes", "/estados-orden", "/mis-ordenes"))
    }

    assert esperados <= presentes


def test_orden_crear_rechaza_campos_extra_en_el_openapi() -> None:
    esquema = app.openapi()["components"]["schemas"]["OrdenCrearRequest"]

    assert esquema.get("additionalProperties") is False
    assert set(esquema["properties"]) == {"vehiculo_id", "falla", "items"}
