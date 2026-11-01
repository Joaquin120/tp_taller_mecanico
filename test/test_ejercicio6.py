"""Pruebas del Ejercicio 6: repositorios y Unit of Work.

Ejecutan la lógica REAL de repositorios, Units of Work y servicios sobre una
base SQLite en memoria (misma infraestructura que las pruebas de C-05). No se
mockean repositorios ni Units of Work; sólo la base es simulada.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.core.auth import UsuarioActual
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.clientes.repository import VehiculoRepository
from app.modules.clientes.unit_of_work import ClientesUnitOfWork
from app.modules.ordenes.models import (
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.ordenes.repository import EstadoOrdenRepository
from app.modules.ordenes.schemas import ItemOrdenRequest, OrdenCrearRequest
from app.modules.ordenes.service import OrdenService
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.repuestos.repository import (
    MovimientoStockRepository,
    RepuestoRepository,
)
from app.modules.repuestos.schemas import (
    ReponerStockRequest,
    RepuestoActualizarRequest,
)
from app.modules.repuestos.service import RepuestoService
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork
from app.modules.usuarios.models import AsignacionRol, Usuario
from app.modules.usuarios.schemas import RegistroClienteRequest
from app.modules.usuarios.service import AuthService
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork
from test.infra_sqlite import SesionFalsa, esquema_sqlite


@pytest.fixture(autouse=True)
def setup_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_secret_ejercicio6_1234567890123")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")


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
        nombre="Admin",
        activo=True,
        debe_cambiar_password=False,
        roles=["ADMIN"],
        roles_token=["ADMIN"],
    )


def actor_mecanico(usuario_id: int = 2) -> UsuarioActual:
    return UsuarioActual(
        id=usuario_id,
        email="mecanico@test.com",
        nombre="Mecánico",
        activo=True,
        debe_cambiar_password=False,
        roles=["MECANICO"],
        roles_token=["MECANICO"],
    )


async def sembrar_catalogo(sesion: SesionFalsa) -> None:
    estados = [
        EstadoOrden(codigo="PENDIENTE", descripcion="Pendiente", posicion=1, es_final=False),
        EstadoOrden(codigo="EN_REPARACION", descripcion="En reparación", posicion=2, es_final=False),
        EstadoOrden(codigo="TERMINADA", descripcion="Terminada", posicion=3, es_final=True),
        EstadoOrden(codigo="CANCELADA", descripcion="Cancelada", posicion=4, es_final=True),
    ]
    for estado in estados:
        await sesion.agregar_y_refrescar(estado)


async def sembrar_cliente_vehiculo(
    sesion: SesionFalsa,
) -> tuple[Cliente, Vehiculo]:
    cliente = Cliente(nombre="Laura", documento="30111222", telefono="1144556677")
    cliente = await sesion.agregar_y_refrescar(cliente)
    vehiculo = Vehiculo(
        cliente_id=cliente.id,
        patente="AA123BB",
        marca="Toyota",
        modelo="Corolla",
        anio=2020,
    )
    vehiculo = await sesion.agregar_y_refrescar(vehiculo)
    return cliente, vehiculo


async def sembrar_repuesto(
    sesion: SesionFalsa,
    codigo: str = "REP-001",
    descripcion: str = "Filtro de aceite",
    precio: str = "100.00",
    stock: int = 10,
) -> Repuesto:
    repuesto = Repuesto(
        codigo=codigo,
        descripcion=descripcion,
        precio=Decimal(precio),
        stock=stock,
    )
    return await sesion.agregar_y_refrescar(repuesto)


async def sembrar_orden_en_reparacion(
    sesion: SesionFalsa,
    vehiculo: Vehiculo,
    repuesto: Repuesto,
    cantidad: int,
    mecanico_id: int = 2,
) -> OrdenTrabajo:
    orden = OrdenTrabajo(
        vehiculo_id=vehiculo.id,
        mecanico_id=mecanico_id,
        estado="EN_REPARACION",
        falla="Falla de prueba",
        total=repuesto.precio * cantidad,
    )
    orden = await sesion.agregar_y_refrescar(orden)
    item = ItemOrden(
        orden_id=orden.id,
        repuesto_id=repuesto.id,
        cantidad=cantidad,
        precio_unitario=repuesto.precio,
    )
    await sesion.agregar_y_refrescar(item)
    await sesion.agregar_y_refrescar(
        HistorialEstadoOrden(
            orden_id=orden.id,
            desde_estado="PENDIENTE",
            hasta_estado="EN_REPARACION",
            usuario_id=mecanico_id,
        )
    )
    return orden


# ---------------------------------------------------------------------------
# A. BaseRepository recibe sesión y modelo
# ---------------------------------------------------------------------------


def test_base_repository_recibe_sesion_y_modelo_en_ambos_ordenes(sesion: SesionFalsa):
    repo_sesion_primero = BaseRepository(sesion, Repuesto)
    repo_modelo_primero = BaseRepository(Repuesto, sesion)

    for repo in (repo_sesion_primero, repo_modelo_primero):
        assert repo.session is sesion
        assert repo.model is Repuesto


def test_base_repository_no_expone_metodos_de_soft_delete():
    assert not hasattr(BaseRepository, "get_by_id_including_deleted")
    assert not hasattr(BaseRepository, "soft_delete")


# ---------------------------------------------------------------------------
# B. SoftDeleteRepository filtra bajas y permite incluirlas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_delete_repository_filtra_y_permite_incluir_borrados(
    sesion: SesionFalsa,
):
    _, vehiculo = await sembrar_cliente_vehiculo(sesion)
    repo = VehiculoRepository(sesion)

    assert await repo.get_by_id(vehiculo.id) is not None
    assert await repo.count() == 1

    await repo.soft_delete(vehiculo)

    assert await repo.get_by_id(vehiculo.id) is None
    assert await repo.get_all() == []
    assert await repo.count() == 0

    incluido = await repo.get_by_id_including_deleted(vehiculo.id)
    assert incluido is not None
    assert incluido.id == vehiculo.id
    assert incluido.borrado_en is not None
    assert isinstance(incluido.borrado_en, datetime)


# ---------------------------------------------------------------------------
# C. Repositorios usan flush y nunca commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repositorios_no_confirman_y_comparten_sesion(sesion: SesionFalsa):
    antes = sesion.contador_commits

    repo = RepuestoRepository(sesion)
    repuesto = await repo.add(
        Repuesto(codigo="X1", descripcion="Prueba", precio=Decimal("10.00"), stock=1)
    )
    assert repuesto.id is not None
    assert sesion.contador_commits == antes

    repuesto.stock = 2
    await repo.update(repuesto)
    assert sesion.contador_commits == antes

    # Todos los repositorios del UoW comparten exactamente la misma sesión.
    uow = RepuestosUnitOfWork(sesion)
    assert uow.session is sesion
    assert uow.repuestos.session is sesion
    assert uow.movimientos.session is sesion
    assert uow.precios.session is sesion

    uow_clientes = ClientesUnitOfWork(sesion)
    assert uow_clientes.clientes.session is sesion
    assert uow_clientes.vehiculos.session is sesion
    assert uow_clientes.ordenes.session is sesion

    uow_ordenes = OrdenesUnitOfWork(sesion)
    for repo in (
        uow_ordenes.ordenes,
        uow_ordenes.items,
        uow_ordenes.historial,
        uow_ordenes.estados,
        uow_ordenes.repuestos,
        uow_ordenes.movimientos,
        uow_ordenes.vehiculos,
    ):
        assert repo.session is sesion


# ---------------------------------------------------------------------------
# I. Catálogo de sólo lectura
# ---------------------------------------------------------------------------


def test_catalogo_es_solo_lectura(sesion: SesionFalsa):
    repo = EstadoOrdenRepository(sesion)

    assert not isinstance(repo, BaseRepository)
    for metodo in ("add", "update", "delete", "soft_delete"):
        assert not hasattr(repo, metodo)


@pytest.mark.asyncio
async def test_catalogo_lista_por_posicion(sesion: SesionFalsa):
    await sembrar_catalogo(sesion)
    sesion.confirmar_siembra()

    estados = await EstadoOrdenRepository(sesion).listar_por_posicion()

    assert [estado.codigo for estado in estados] == [
        "PENDIENTE",
        "EN_REPARACION",
        "TERMINADA",
        "CANCELADA",
    ]


# ---------------------------------------------------------------------------
# H. RN-02: un solo bloque transaccional
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rn02_registro_en_un_solo_commit(sesion: SesionFalsa):
    antes = sesion.contador_commits

    usuario, roles, cliente_id = await AuthService.registrar_cliente(
        RegistroClienteRequest(
            email="nuevo@test.com",
            password="Secreta123",
            nombre="Nuevo",
            documento="12345678",
            telefono="1144556677",
        ),
        UsuariosUnitOfWork(sesion),
    )

    assert sesion.contador_commits - antes == 1
    assert usuario.id is not None
    assert roles == ["CLIENTE"]
    assert cliente_id is not None
    assert sesion.contar(Usuario) == 1
    assert sesion.contar(AsignacionRol) == 1
    assert sesion.contar(Cliente) == 1


# ---------------------------------------------------------------------------
# H. RN-20: precio e historial en un solo bloque transaccional
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rn20_cambio_de_precio_registra_historial_en_un_solo_commit(
    sesion: SesionFalsa,
):
    repuesto = await sembrar_repuesto(sesion)
    sesion.confirmar_siembra()
    antes = sesion.contador_commits

    response = await RepuestoService.actualizar(
        repuesto.id,
        RepuestoActualizarRequest(precio=Decimal("150.00")),
        actor_admin(),
        RepuestosUnitOfWork(sesion),
    )

    assert sesion.contador_commits - antes == 1
    assert response.precio == Decimal("150.00")

    historial = sesion.listar(HistorialPrecioRepuesto)
    assert len(historial) == 1
    assert historial[0].precio_anterior == Decimal("100.00")
    assert historial[0].precio_nuevo == Decimal("150.00")

    # Un PATCH que no cambia el precio no deja línea nueva.
    antes = sesion.contador_commits
    await RepuestoService.actualizar(
        repuesto.id,
        RepuestoActualizarRequest(precio=Decimal("150.00")),
        actor_admin(),
        RepuestosUnitOfWork(sesion),
    )
    assert sesion.contador_commits - antes == 1
    assert len(sesion.listar(HistorialPrecioRepuesto)) == 1


# ---------------------------------------------------------------------------
# J. RN-14: escritura de stock centralizada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rn14_reposicion_y_terminacion_usan_el_mismo_punto_de_escritura(
    sesion: SesionFalsa,
    monkeypatch: pytest.MonkeyPatch,
):
    llamadas: list[str] = []
    original = MovimientoStockRepository.registrar_movimiento

    async def espia(self, **kwargs):
        llamadas.append(kwargs["motivo"])
        return await original(self, **kwargs)

    monkeypatch.setattr(MovimientoStockRepository, "registrar_movimiento", espia)

    await sembrar_catalogo(sesion)
    _, vehiculo = await sembrar_cliente_vehiculo(sesion)
    repuesto = await sembrar_repuesto(sesion, stock=10)
    orden = await sembrar_orden_en_reparacion(sesion, vehiculo, repuesto, cantidad=2)
    sesion.confirmar_siembra()

    await RepuestoService.reponer(
        repuesto.id,
        ReponerStockRequest(cantidad=5),
        actor_admin(),
        RepuestosUnitOfWork(sesion),
    )
    await OrdenService.terminar_orden(
        orden.id,
        actor_mecanico(),
        OrdenesUnitOfWork(sesion),
    )

    assert len(llamadas) == 2
    assert llamadas[0] == "Reposición de stock"
    assert llamadas[1] == "Salida por orden 1"


# ---------------------------------------------------------------------------
# H. RN-13: terminación de orden en un solo bloque transaccional
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rn13_terminar_orden_descuenta_stock_en_un_solo_commit(
    sesion: SesionFalsa,
):
    await sembrar_catalogo(sesion)
    _, vehiculo = await sembrar_cliente_vehiculo(sesion)
    repuesto = await sembrar_repuesto(sesion, stock=10)
    orden = await sembrar_orden_en_reparacion(sesion, vehiculo, repuesto, cantidad=2)
    sesion.confirmar_siembra()
    antes = sesion.contador_commits

    response = await OrdenService.terminar_orden(
        orden.id,
        actor_mecanico(),
        OrdenesUnitOfWork(sesion),
    )

    assert sesion.contador_commits - antes == 1
    assert response.estado == "TERMINADA"

    repuesto_db = sesion.listar(Repuesto)[0]
    assert repuesto_db.stock == 8

    movimientos = sesion.listar(MovimientoStock)
    assert len(movimientos) == 1
    assert movimientos[0].cantidad == -2
    assert movimientos[0].orden_id == orden.id

    orden_db = sesion.listar(OrdenTrabajo)[0]
    assert orden_db.estado == "TERMINADA"
    assert len(sesion.listar(HistorialEstadoOrden)) == 2


@pytest.mark.asyncio
async def test_rn13_stock_insuficiente_revierte_todo(sesion: SesionFalsa):
    await sembrar_catalogo(sesion)
    _, vehiculo = await sembrar_cliente_vehiculo(sesion)
    repuesto = await sembrar_repuesto(sesion, stock=1)
    orden = await sembrar_orden_en_reparacion(sesion, vehiculo, repuesto, cantidad=4)
    sesion.confirmar_siembra()
    antes = sesion.contador_commits

    with pytest.raises(HTTPException) as exc_info:
        await OrdenService.terminar_orden(
            orden.id,
            actor_mecanico(),
            OrdenesUnitOfWork(sesion),
        )

    assert exc_info.value.status_code == 409
    assert sesion.contador_commits == antes
    assert sesion.listar(Repuesto)[0].stock == 1
    assert sesion.listar(MovimientoStock) == []
    assert sesion.listar(OrdenTrabajo)[0].estado == "EN_REPARACION"
    assert len(sesion.listar(HistorialEstadoOrden)) == 1


# ---------------------------------------------------------------------------
# Extra: alta de orden copia precios y calcula total (valida el flujo nuevo)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crear_orden_copia_precios_y_calcula_total(sesion: SesionFalsa):
    await sembrar_catalogo(sesion)
    _, vehiculo = await sembrar_cliente_vehiculo(sesion)
    repuesto_1 = await sembrar_repuesto(sesion, "R1", "Filtro", "100.00", 10)
    repuesto_2 = await sembrar_repuesto(sesion, "R2", "Aceite", "50.00", 10)
    sesion.confirmar_siembra()
    antes = sesion.contador_commits

    response = await OrdenService.crear_orden(
        OrdenCrearRequest(
            vehiculo_id=vehiculo.id,
            falla="Ruido al frenar",
            items=[
                ItemOrdenRequest(repuesto_id=repuesto_1.id, cantidad=2),
                ItemOrdenRequest(repuesto_id=repuesto_2.id, cantidad=3),
            ],
        ),
        actor_admin(),
        OrdenesUnitOfWork(sesion),
    )

    assert sesion.contador_commits - antes == 1
    assert response.estado == "PENDIENTE"
    assert response.total == Decimal("350.00")
    assert len(response.items) == 2
    assert response.items[0].precio_unitario == Decimal("100.00")
    assert response.items[0].subtotal == Decimal("200.00")
    assert response.historial[0].hasta_estado == "PENDIENTE"
