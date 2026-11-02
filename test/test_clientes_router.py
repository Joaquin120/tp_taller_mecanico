"""Pruebas de endpoints de clientes y vehículos (router y RBAC)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import pytest
from httpx import ASGITransport, AsyncClient

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

from app.core.auth import UsuarioActual, get_current_user
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.clientes.router import get_clientes_uow
from app.modules.clientes.unit_of_work import ClientesUnitOfWork
from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo
from app.modules.usuarios.models import Usuario
from main import app
from test.infra_sqlite import SesionFalsa, esquema_sqlite


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_for_clientes_router_123")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    app.state.dummy_hash = "$2b$04$dummyhashfordefensetimingtestingonly1234567890123456789012"
    mock_sf = MagicMock()
    mock_sf.return_value.__aenter__.return_value = AsyncMock()
    app.state.session_factory = mock_sf


@pytest.fixture
async def sesion():
    gen = esquema_sqlite()
    base: SesionFalsa = next(gen)
    try:
        yield base
    finally:
        gen.close()


def actor_admin(id: int = 1) -> UsuarioActual:
    return UsuarioActual(
        id=id,
        email="admin@test.com",
        nombre="Admin",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
    )


def actor_recepcion(id: int = 2) -> UsuarioActual:
    return UsuarioActual(
        id=id,
        email="recepcion@test.com",
        nombre="Recepcion",
        activo=True,
        debe_cambiar_password=False,
        roles=["RECEPCION"],
    )


def actor_mecanico(id: int = 3) -> UsuarioActual:
    return UsuarioActual(
        id=id,
        email="mecanico@test.com",
        nombre="Mecanico",
        activo=True,
        debe_cambiar_password=False,
        roles=["MECANICO"],
    )


def actor_cliente(id: int = 4) -> UsuarioActual:
    return UsuarioActual(
        id=id,
        email="cliente@test.com",
        nombre="Cliente",
        activo=True,
        debe_cambiar_password=False,
        roles=["CLIENTE"],
    )


async def sembrar_estados(sesion: SesionFalsa) -> None:
    estados = [
        EstadoOrden(codigo="PENDIENTE", descripcion="Pendiente", posicion=1, es_final=False),
        EstadoOrden(codigo="EN_REPARACION", descripcion="En reparación", posicion=2, es_final=False),
        EstadoOrden(codigo="TERMINADA", descripcion="Terminada", posicion=3, es_final=True),
        EstadoOrden(codigo="CANCELADA", descripcion="Cancelada", posicion=4, es_final=True),
    ]
    for estado in estados:
        await sesion.agregar_y_refrescar(estado)
    sesion.confirmar_siembra()


# ============================================================================
# POST /clientes
# ============================================================================

@pytest.mark.asyncio
async def test_crear_cliente_exitoso_201(sesion: SesionFalsa):
    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_recepcion(2)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/clientes",
                json={
                    "nombre": "Carlos Perez",
                    "documento": "28111222",
                    "telefono": "1144556677",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] is not None
        assert data["nombre"] == "Carlos Perez"
        assert data["documento"] == "28111222"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_crear_cliente_documento_duplicado_409(sesion: SesionFalsa):
    c1 = Cliente(nombre="Carlos Perez", documento="28111222", telefono="111")
    await sesion.agregar_y_refrescar(c1)
    sesion.confirmar_siembra()

    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_admin(1)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/clientes",
                json={
                    "nombre": "Carlos Clon",
                    "documento": "28111222",
                    "telefono": "222",
                },
            )
        assert resp.status_code == 409
        assert "documento" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_crear_cliente_extra_field_422(sesion: SesionFalsa):
    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_admin(1)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/clientes",
                json={
                    "nombre": "Carlos Perez",
                    "documento": "28111222",
                    "telefono": "111",
                    "campo_invalido": "hack",
                },
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_crear_cliente_sin_sesion_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/clientes",
            json={"nombre": "A", "documento": "1", "telefono": "2"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_crear_cliente_rol_insuficiente_403(sesion: SesionFalsa):
    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_mecanico(3)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/clientes",
                json={"nombre": "A", "documento": "1", "telefono": "2"},
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# GET /clientes/{id}
# ============================================================================

@pytest.mark.asyncio
async def test_obtener_cliente_con_vehiculos_200(sesion: SesionFalsa):
    c = Cliente(nombre="Laura", documento="30111", telefono="111")
    c = await sesion.agregar_y_refrescar(c)
    v = Vehiculo(cliente_id=c.id, patente="AA111BB", marca="Toyota", modelo="Corolla", anio=2020)
    await sesion.agregar_y_refrescar(v)
    sesion.confirmar_siembra()

    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_admin(1)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/clientes/{c.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == c.id
        assert len(data["vehiculos"]) == 1
        assert data["vehiculos"][0]["patente"] == "AA111BB"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_obtener_cliente_inexistente_404(sesion: SesionFalsa):
    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_admin(1)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/clientes/999")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# POST /clientes/{id}/vehiculos
# ============================================================================

@pytest.mark.asyncio
async def test_crear_vehiculo_exitoso_201(sesion: SesionFalsa):
    c = Cliente(nombre="Mario", documento="40111", telefono="111")
    c = await sesion.agregar_y_refrescar(c)
    sesion.confirmar_siembra()

    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_recepcion(2)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/clientes/{c.id}/vehiculos",
                json={
                    "patente": "ab 123 cd",
                    "marca": "Toyota",
                    "modelo": "Yaris",
                    "anio": 2021,
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] is not None
        assert data["patente"] == "AB 123 CD".strip().upper()
        assert data["cliente_id"] == c.id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_crear_vehiculo_anio_invalido_422(sesion: SesionFalsa):
    c = Cliente(nombre="Mario", documento="40111", telefono="111")
    c = await sesion.agregar_y_refrescar(c)
    sesion.confirmar_siembra()

    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_admin(1)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/clientes/{c.id}/vehiculos",
                json={
                    "patente": "AA123BB",
                    "marca": "Ford",
                    "modelo": "T",
                    "anio": 1920,  # ge=1950
                },
            )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_crear_vehiculo_patente_duplicada_409(sesion: SesionFalsa):
    c = Cliente(nombre="Mario", documento="40111", telefono="111")
    c = await sesion.agregar_y_refrescar(c)
    v = Vehiculo(cliente_id=c.id, patente="AA123BB", marca="Fiat", modelo="Uno", anio=2010)
    await sesion.agregar_y_refrescar(v)
    sesion.confirmar_siembra()

    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_admin(1)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/clientes/{c.id}/vehiculos",
                json={
                    "patente": "AA123BB",
                    "marca": "VW",
                    "modelo": "Gol",
                    "anio": 2012,
                },
            )
        assert resp.status_code == 409
        assert "patente" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# DELETE /vehiculos/{id}
# ============================================================================

@pytest.mark.asyncio
async def test_baja_vehiculo_exitoso_204(sesion: SesionFalsa):
    await sembrar_estados(sesion)
    c = Cliente(nombre="Mario", documento="40111", telefono="111")
    c = await sesion.agregar_y_refrescar(c)
    v = Vehiculo(cliente_id=c.id, patente="AA123BB", marca="Fiat", modelo="Uno", anio=2010)
    v = await sesion.agregar_y_refrescar(v)
    sesion.confirmar_siembra()

    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_admin(1)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/vehiculos/{v.id}")
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_baja_vehiculo_rechazada_orden_abierta_409_rn16(sesion: SesionFalsa):
    await sembrar_estados(sesion)
    c = Cliente(nombre="Mario", documento="40111", telefono="111")
    c = await sesion.agregar_y_refrescar(c)
    v = Vehiculo(cliente_id=c.id, patente="AA123BB", marca="Fiat", modelo="Uno", anio=2010)
    v = await sesion.agregar_y_refrescar(v)
    orden = OrdenTrabajo(vehiculo_id=v.id, estado="PENDIENTE", falla="Falla motor")
    await sesion.agregar_y_refrescar(orden)
    sesion.confirmar_siembra()

    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_recepcion(2)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete(f"/vehiculos/{v.id}")
        assert resp.status_code == 409
        assert "abiertas" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_baja_vehiculo_rol_insuficiente_403(sesion: SesionFalsa):
    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_cliente(4)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/vehiculos/1")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# GET /mis-vehiculos (RN-17)
# ============================================================================

@pytest.mark.asyncio
async def test_mis_vehiculos_exitoso_200(sesion: SesionFalsa):
    usr = Usuario(email="cliente@test.com", nombre="Cliente Laura", password_hash="h", activo=True)
    usr = await sesion.agregar_y_refrescar(usr)
    c = Cliente(usuario_id=usr.id, nombre="Laura", documento="50111", telefono="111")
    c = await sesion.agregar_y_refrescar(c)
    v1 = Vehiculo(cliente_id=c.id, patente="LAU111", marca="Toyota", modelo="Yaris", anio=2020)
    v2 = Vehiculo(cliente_id=c.id, patente="LAU222", marca="Ford", modelo="Focus", anio=2017)
    await sesion.agregar_y_refrescar(v1)
    await sesion.agregar_y_refrescar(v2)
    sesion.confirmar_siembra()

    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_cliente(usr.id)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/mis-vehiculos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        patentes = [item["patente"] for item in data]
        assert "LAU111" in patentes
        assert "LAU222" in patentes
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_mis_vehiculos_sin_sesion_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/mis-vehiculos")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mis_vehiculos_rol_no_cliente_403(sesion: SesionFalsa):
    app.dependency_overrides[get_clientes_uow] = lambda: ClientesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor_mecanico(3)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/mis-vehiculos")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
