"""Pruebas unitarias de servicios de clientes y vehículos con lógica real sobre SQLite."""

from datetime import datetime
import pytest
from fastapi import HTTPException

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.clientes.schemas import ClienteCreateRequest, VehiculoCreateRequest
from app.modules.clientes.service import ClienteService, VehiculoService
from app.modules.clientes.unit_of_work import ClientesUnitOfWork
from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo
from app.modules.usuarios.models import Usuario
from test.infra_sqlite import SesionFalsa, esquema_sqlite


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_for_clientes_service_123")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")


@pytest.fixture
async def sesion():
    gen = esquema_sqlite()
    base: SesionFalsa = next(gen)
    try:
        yield base
    finally:
        gen.close()


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
# ClienteService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_crear_cliente_exitoso(sesion: SesionFalsa):
    uow = ClientesUnitOfWork(sesion)
    req = ClienteCreateRequest(
        nombre="Laura Gomez",
        documento="30111222",
        telefono="1144556677",
    )
    cliente = await ClienteService.crear_cliente(req, uow)

    assert cliente.id is not None
    assert cliente.nombre == "Laura Gomez"
    assert cliente.documento == "30111222"
    assert cliente.telefono == "1144556677"


@pytest.mark.asyncio
async def test_crear_cliente_documento_duplicado_409(sesion: SesionFalsa):
    uow = ClientesUnitOfWork(sesion)
    req1 = ClienteCreateRequest(
        nombre="Laura Gomez",
        documento="30111222",
        telefono="1144556677",
    )
    await ClienteService.crear_cliente(req1, uow)

    req2 = ClienteCreateRequest(
        nombre="Laura Clon",
        documento="30111222",
        telefono="1199887766",
    )
    with pytest.raises(HTTPException) as exc_info:
        await ClienteService.crear_cliente(req2, uow)

    assert exc_info.value.status_code == 409
    assert "documento" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_obtener_cliente_con_vehiculos_exitoso(sesion: SesionFalsa):
    cliente = Cliente(nombre="Jorge", documento="20333444", telefono="1122334455")
    cliente = await sesion.agregar_y_refrescar(cliente)

    v1 = Vehiculo(cliente_id=cliente.id, patente="AA111BB", marca="Ford", modelo="Fiesta", anio=2018)
    v2 = Vehiculo(cliente_id=cliente.id, patente="AA222BB", marca="Fiat", modelo="Cronos", anio=2021)
    await sesion.agregar_y_refrescar(v1)
    await sesion.agregar_y_refrescar(v2)
    sesion.confirmar_siembra()

    uow = ClientesUnitOfWork(sesion)
    cliente_db = await ClienteService.obtener_cliente(cliente.id, uow)

    assert cliente_db.id == cliente.id
    assert len(cliente_db.vehiculos) == 2
    patentes = [v.patente for v in cliente_db.vehiculos]
    assert "AA111BB" in patentes
    assert "AA222BB" in patentes


@pytest.mark.asyncio
async def test_obtener_cliente_inexistente_404(sesion: SesionFalsa):
    uow = ClientesUnitOfWork(sesion)
    with pytest.raises(HTTPException) as exc_info:
        await ClienteService.obtener_cliente(999, uow)

    assert exc_info.value.status_code == 404
    assert "no encontrado" in exc_info.value.detail.lower()


# ============================================================================
# VehiculoService Tests
# ============================================================================

@pytest.mark.asyncio
async def test_crear_vehiculo_exitoso(sesion: SesionFalsa):
    cliente = Cliente(nombre="Mario", documento="40123456", telefono="1199990000")
    cliente = await sesion.agregar_y_refrescar(cliente)
    sesion.confirmar_siembra()

    uow = ClientesUnitOfWork(sesion)
    req = VehiculoCreateRequest(
        patente="ab 123 cd",  # Prueba normalización a AB123CD
        marca="Toyota",
        modelo="Corolla",
        anio=2020,
    )
    vehiculo = await VehiculoService.crear_vehiculo(cliente.id, req, uow)

    assert vehiculo.id is not None
    assert vehiculo.cliente_id == cliente.id
    assert vehiculo.patente == "AB 123 CD".replace(" ", "").upper() or vehiculo.patente == "AB 123 CD".strip().upper()
    assert vehiculo.anio == 2020
    assert vehiculo.borrado_en is None


@pytest.mark.asyncio
async def test_crear_vehiculo_cliente_inexistente_404(sesion: SesionFalsa):
    uow = ClientesUnitOfWork(sesion)
    req = VehiculoCreateRequest(
        patente="AA999ZZ",
        marca="Honda",
        modelo="Civic",
        anio=2019,
    )
    with pytest.raises(HTTPException) as exc_info:
        await VehiculoService.crear_vehiculo(999, req, uow)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_crear_vehiculo_patente_duplicada_vigente_409(sesion: SesionFalsa):
    cliente = Cliente(nombre="Mario", documento="40123456", telefono="1199990000")
    cliente = await sesion.agregar_y_refrescar(cliente)
    v1 = Vehiculo(cliente_id=cliente.id, patente="AA123BB", marca="Toyota", modelo="Yaris", anio=2020)
    await sesion.agregar_y_refrescar(v1)
    sesion.confirmar_siembra()

    uow = ClientesUnitOfWork(sesion)
    req = VehiculoCreateRequest(
        patente="AA123BB",
        marca="Renault",
        modelo="Clio",
        anio=2015,
    )
    with pytest.raises(HTTPException) as exc_info:
        await VehiculoService.crear_vehiculo(cliente.id, req, uow)

    assert exc_info.value.status_code == 409
    assert "patente" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_crear_vehiculo_reutiliza_patente_dada_de_baja_c19(sesion: SesionFalsa):
    """C-19: Un vehículo dado de baja permite que otro cliente registre la misma patente."""
    cliente1 = Cliente(nombre="Cliente 1", documento="11111111", telefono="111")
    cliente1 = await sesion.agregar_y_refrescar(cliente1)
    v_baja = Vehiculo(
        cliente_id=cliente1.id,
        patente="AA555ZZ",
        marca="Ford",
        modelo="Ka",
        anio=2010,
        borrado_en=datetime.now(),
    )
    await sesion.agregar_y_refrescar(v_baja)

    cliente2 = Cliente(nombre="Cliente 2", documento="22222222", telefono="222")
    cliente2 = await sesion.agregar_y_refrescar(cliente2)
    sesion.confirmar_siembra()

    uow = ClientesUnitOfWork(sesion)
    req = VehiculoCreateRequest(
        patente="AA555ZZ",
        marca="Chevrolet",
        modelo="Cruze",
        anio=2022,
    )
    nuevo_vehiculo = await VehiculoService.crear_vehiculo(cliente2.id, req, uow)

    assert nuevo_vehiculo.id is not None
    assert nuevo_vehiculo.id != v_baja.id
    assert nuevo_vehiculo.patente == "AA555ZZ"
    assert nuevo_vehiculo.cliente_id == cliente2.id


@pytest.mark.asyncio
async def test_baja_vehiculo_rechazada_por_orden_abierta_rn16(sesion: SesionFalsa):
    """RN-16: Un vehículo con órdenes abiertas (es_final=False) rechaza la baja con 409."""
    await sembrar_estados(sesion)

    cliente = Cliente(nombre="Ana", documento="35555666", telefono="333")
    cliente = await sesion.agregar_y_refrescar(cliente)
    vehiculo = Vehiculo(cliente_id=cliente.id, patente="BB123CC", marca="VW", modelo="Golf", anio=2020)
    vehiculo = await sesion.agregar_y_refrescar(vehiculo)

    orden_abierta = OrdenTrabajo(
        vehiculo_id=vehiculo.id,
        estado="EN_REPARACION",  # es_final=False
        falla="Frenos ruidosos",
    )
    await sesion.agregar_y_refrescar(orden_abierta)
    sesion.confirmar_siembra()

    uow = ClientesUnitOfWork(sesion)
    with pytest.raises(HTTPException) as exc_info:
        await VehiculoService.baja_vehiculo(vehiculo.id, uow)

    assert exc_info.value.status_code == 409
    assert "abiertas" in exc_info.value.detail.lower()

    # Verificar que el vehículo sigue activo
    v_actual = await uow.vehiculos.get_by_id(vehiculo.id)
    assert v_actual is not None
    assert v_actual.borrado_en is None


@pytest.mark.asyncio
async def test_baja_vehiculo_exitosa_con_ordenes_finalizadas(sesion: SesionFalsa):
    """Baja lógica permitida si las órdenes están en estado final (es_final=True)."""
    await sembrar_estados(sesion)

    cliente = Cliente(nombre="Ana", documento="35555666", telefono="333")
    cliente = await sesion.agregar_y_refrescar(cliente)
    vehiculo = Vehiculo(cliente_id=cliente.id, patente="BB123CC", marca="VW", modelo="Golf", anio=2020)
    vehiculo = await sesion.agregar_y_refrescar(vehiculo)

    orden_terminada = OrdenTrabajo(
        vehiculo_id=vehiculo.id,
        estado="TERMINADA",  # es_final=True
        falla="Cambio de aceite",
    )
    await sesion.agregar_y_refrescar(orden_terminada)
    sesion.confirmar_siembra()

    uow = ClientesUnitOfWork(sesion)
    await VehiculoService.baja_vehiculo(vehiculo.id, uow)

    # El vehículo ya no se lista como activo
    v_activo = await uow.vehiculos.get_by_id(vehiculo.id)
    assert v_activo is None

    # Pero existe con borrado_en
    v_borrado = await uow.vehiculos.get_by_id_including_deleted(vehiculo.id)
    assert v_borrado is not None
    assert v_borrado.borrado_en is not None


@pytest.mark.asyncio
async def test_baja_vehiculo_inexistente_404(sesion: SesionFalsa):
    uow = ClientesUnitOfWork(sesion)
    with pytest.raises(HTTPException) as exc_info:
        await VehiculoService.baja_vehiculo(999, uow)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_listar_mis_vehiculos_rn17(sesion: SesionFalsa):
    """RN-17: El cliente sólo ve sus vehículos vigentes y ninguno ajeno o borrado."""
    # Usuario y Cliente Laura
    usr_laura = Usuario(email="laura@test.com", nombre="Laura", password_hash="h1", activo=True)
    usr_laura = await sesion.agregar_y_refrescar(usr_laura)
    cli_laura = Cliente(usuario_id=usr_laura.id, nombre="Laura", documento="30111", telefono="111")
    cli_laura = await sesion.agregar_y_refrescar(cli_laura)

    v_laura_activo = Vehiculo(cliente_id=cli_laura.id, patente="LAU001", marca="Toyota", modelo="Etios", anio=2019)
    v_laura_borrado = Vehiculo(cliente_id=cli_laura.id, patente="LAU002", marca="Toyota", modelo="Corolla", anio=2015, borrado_en=datetime.now())
    await sesion.agregar_y_refrescar(v_laura_activo)
    await sesion.agregar_y_refrescar(v_laura_borrado)

    # Usuario y Cliente Pedro (otro cliente)
    usr_pedro = Usuario(email="pedro@test.com", nombre="Pedro", password_hash="h2", activo=True)
    usr_pedro = await sesion.agregar_y_refrescar(usr_pedro)
    cli_pedro = Cliente(usuario_id=usr_pedro.id, nombre="Pedro", documento="30222", telefono="222")
    cli_pedro = await sesion.agregar_y_refrescar(cli_pedro)
    v_pedro = Vehiculo(cliente_id=cli_pedro.id, patente="PED001", marca="Peugeot", modelo="208", anio=2021)
    await sesion.agregar_y_refrescar(v_pedro)

    sesion.confirmar_siembra()

    uow = ClientesUnitOfWork(sesion)
    # Laura consulta sus vehículos
    mis_vehiculos = await VehiculoService.listar_mis_vehiculos(usr_laura.id, uow)

    assert len(mis_vehiculos) == 1
    assert mis_vehiculos[0].patente == "LAU001"
    assert mis_vehiculos[0].id != v_pedro.id
    assert mis_vehiculos[0].id != v_laura_borrado.id

    # Usuario sin cliente asociado devuelve lista vacía
    usr_solo = Usuario(email="sincliente@test.com", nombre="Sin Cliente", password_hash="h3", activo=True)
    usr_solo = await sesion.agregar_y_refrescar(usr_solo)
    sesion.confirmar_siembra()

    vacios = await VehiculoService.listar_mis_vehiculos(usr_solo.id, uow)
    assert vacios == []
