"""Datos y utilidades compartidas por las pruebas del módulo de órdenes (C-08)."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator

import app.modules.clientes.models  # noqa: F401
import app.modules.ordenes.models  # noqa: F401
import app.modules.repuestos.models  # noqa: F401
import app.modules.usuarios.models  # noqa: F401

from app.core.auth import UsuarioActual, get_current_user
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import (
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.ordenes.router import get_ordenes_uow
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.repuestos.models import Repuesto
from app.modules.usuarios.models import Usuario
from main import app
from test.infra_sqlite import SesionFalsa

AHORA = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

ESTADOS = [
    ("PENDIENTE", "Orden creada pendiente de revisión", 1, False),
    ("EN_REPARACION", "Vehículo en proceso de reparación", 2, False),
    ("TERMINADA", "Reparación finalizada con éxito", 3, True),
    ("CANCELADA", "Orden cancelada", 4, True),
]


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
        nombre="Recepción",
        activo=True,
        debe_cambiar_password=False,
        roles=["RECEPCION"],
    )


def actor_mecanico(id: int = 3) -> UsuarioActual:
    return UsuarioActual(
        id=id,
        email="mecanico@test.com",
        nombre="Mecánico",
        activo=True,
        debe_cambiar_password=False,
        roles=["MECANICO"],
    )


def actor_cliente(id: int = 4, cliente_id: int | None = 1) -> UsuarioActual:
    return UsuarioActual(
        id=id,
        email="cliente@test.com",
        nombre="Cliente",
        activo=True,
        debe_cambiar_password=False,
        roles=["CLIENTE"],
        cliente_id=cliente_id,
    )


async def sembrar_estados(sesion: SesionFalsa) -> None:
    for codigo, descripcion, posicion, es_final in ESTADOS:
        await sesion.agregar_y_refrescar(
            EstadoOrden(
                codigo=codigo,
                descripcion=descripcion,
                posicion=posicion,
                es_final=es_final,
            )
        )


async def sembrar_usuario(
    sesion: SesionFalsa,
    email: str,
    nombre: str = "Usuario de prueba",
) -> Usuario:
    usuario = Usuario(
        email=email,
        nombre=nombre,
        password_hash="$2b$04$hashdepruebasuficientementelargo000000000000000000000000",
        activo=True,
        debe_cambiar_password=False,
    )
    return await sesion.agregar_y_refrescar(usuario)


async def sembrar_cliente(
    sesion: SesionFalsa,
    documento: str = "30111222",
    usuario_id: int | None = None,
    nombre: str = "Laura Gómez",
) -> Cliente:
    cliente = Cliente(
        usuario_id=usuario_id,
        nombre=nombre,
        documento=documento,
        telefono="1144556677",
    )
    return await sesion.agregar_y_refrescar(cliente)


async def sembrar_vehiculo(
    sesion: SesionFalsa,
    cliente_id: int,
    patente: str = "AA123BB",
) -> Vehiculo:
    vehiculo = Vehiculo(
        cliente_id=cliente_id,
        patente=patente,
        marca="Toyota",
        modelo="Corolla",
        anio=2020,
    )
    return await sesion.agregar_y_refrescar(vehiculo)


async def sembrar_repuesto(
    sesion: SesionFalsa,
    codigo: str,
    precio: str = "100.00",
    stock: int = 10,
    descripcion: str = "Repuesto de prueba",
) -> Repuesto:
    repuesto = Repuesto(
        codigo=codigo,
        descripcion=descripcion,
        precio=Decimal(precio),
        stock=stock,
    )
    return await sesion.agregar_y_refrescar(repuesto)


async def sembrar_orden(
    sesion: SesionFalsa,
    vehiculo_id: int,
    usuario_id: int,
    estado: str = "PENDIENTE",
    mecanico_id: int | None = None,
    items: list[tuple[Repuesto, int]] | None = None,
    falla: str = "Falla de prueba",
) -> OrdenTrabajo:
    total = Decimal("0.00")
    orden = OrdenTrabajo(
        vehiculo_id=vehiculo_id,
        mecanico_id=mecanico_id,
        estado=estado,
        falla=falla,
        total=Decimal("0.00"),
        creada_en=AHORA,
    )
    orden = await sesion.agregar_y_refrescar(orden)

    for repuesto, cantidad in items or []:
        total += repuesto.precio * cantidad
        await sesion.agregar_y_refrescar(
            ItemOrden(
                orden_id=orden.id,
                repuesto_id=repuesto.id,
                cantidad=cantidad,
                precio_unitario=repuesto.precio,
            )
        )

    orden.total = total
    await sesion.flush()

    await sesion.agregar_y_refrescar(
        HistorialEstadoOrden(
            orden_id=orden.id,
            desde_estado=None,
            hasta_estado="PENDIENTE",
            usuario_id=usuario_id,
            cuando=AHORA,
        )
    )
    # La orden sembrada representa una precondición real: se confirma fuera del
    # UoW bajo prueba para que un rollback posterior no la descarte.
    sesion.confirmar_siembra()
    return orden


async def sembrar_escenario(sesion: SesionFalsa) -> dict[str, Any]:
    """Siembra estados, usuarios, clientes, vehículos y repuestos de prueba."""
    await sembrar_estados(sesion)

    admin = await sembrar_usuario(sesion, "admin@example.com", "Admin")
    recepcion = await sembrar_usuario(sesion, "recepcion@example.com", "Recepción")
    mecanico = await sembrar_usuario(sesion, "mecanico@example.com", "Mecánico")
    otro_mecanico = await sembrar_usuario(sesion, "mecanico2@example.com", "Otro")
    cliente_user = await sembrar_usuario(sesion, "cliente@example.com", "Laura")

    cliente = await sembrar_cliente(
        sesion,
        documento="30111222",
        usuario_id=cliente_user.id,
        nombre="Laura Gómez",
    )
    cliente_ajeno = await sembrar_cliente(
        sesion,
        documento="25333444",
        usuario_id=None,
        nombre="Jorge Pérez",
    )

    vehiculo = await sembrar_vehiculo(sesion, cliente.id, "AA123BB")
    vehiculo_ajeno = await sembrar_vehiculo(sesion, cliente_ajeno.id, "AD789EE")

    repuesto_1 = await sembrar_repuesto(
        sesion, "REP-001", "100.00", 10, "Filtro de aceite"
    )
    repuesto_2 = await sembrar_repuesto(
        sesion, "REP-002", "250.00", 3, "Pastillas de freno"
    )
    repuesto_3 = await sembrar_repuesto(sesion, "REP-003", "50.00", 100, "Bujía")
    repuesto_4 = await sembrar_repuesto(sesion, "REP-004", "10.00", 100, "Aceite")

    sesion.confirmar_siembra()

    return {
        "admin": admin,
        "recepcion": recepcion,
        "mecanico": mecanico,
        "otro_mecanico": otro_mecanico,
        "cliente_user": cliente_user,
        "cliente": cliente,
        "cliente_ajeno": cliente_ajeno,
        "vehiculo": vehiculo,
        "vehiculo_ajeno": vehiculo_ajeno,
        "repuesto_1": repuesto_1,
        "repuesto_2": repuesto_2,
        "repuesto_3": repuesto_3,
        "repuesto_4": repuesto_4,
    }


@contextmanager
def con_overrides(sesion: SesionFalsa, actor: UsuarioActual) -> Iterator[None]:
    """Conecta el UoW real y el actor autenticado a la app para pruebas de router."""
    app.dependency_overrides[get_ordenes_uow] = lambda: OrdenesUnitOfWork(sesion)
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        yield
    finally:
        app.dependency_overrides.clear()
