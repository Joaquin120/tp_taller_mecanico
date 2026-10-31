import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import bcrypt
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.database import crear_motor
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import (
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    Usuario,
)


def hash_password(password: str, rounds: int) -> str:
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


async def seed() -> None:
    settings = get_settings()
    engine = crear_motor(settings.database_url, pool_size=5, echo=settings.SQL_ECHO)

    async with AsyncSession(engine) as session:
        # 1. TRUNCATE limpio con CASCADE para omitir triggers FOR EACH ROW
        await session.execute(
            text(
                """
                TRUNCATE TABLE
                    historial_precio_repuesto,
                    movimiento_stock,
                    historial_estado_orden,
                    item_orden,
                    orden_trabajo,
                    vehiculo,
                    cliente,
                    repuesto,
                    estado_orden,
                    asignacion_rol,
                    intento_acceso,
                    evento_seguridad,
                    usuario
                RESTART IDENTITY CASCADE;
                """
            )
        )
        await session.commit()

        # 2. Catálogo de estados de orden
        estados = [
            EstadoOrden(
                codigo="PENDIENTE",
                descripcion="Orden creada pendiente de revisión",
                posicion=1,
                es_final=False,
            ),
            EstadoOrden(
                codigo="EN_REPARACION",
                descripcion="Vehículo en proceso de reparación",
                posicion=2,
                es_final=False,
            ),
            EstadoOrden(
                codigo="TERMINADA",
                descripcion="Reparación finalizada con éxito",
                posicion=3,
                es_final=True,
            ),
            EstadoOrden(
                codigo="CANCELADA",
                descripcion="Orden cancelada",
                posicion=4,
                es_final=True,
            ),
        ]
        session.add_all(estados)
        await session.flush()

        # 3. Usuarios de prueba
        default_pwd_hash = hash_password("Password123!", settings.BCRYPT_ROUNDS)

        admin = Usuario(
            email="admin@example.com",
            nombre="Administrador General",
            password_hash=default_pwd_hash,
            activo=True,
            debe_cambiar_password=False,
        )
        admin2 = Usuario(
            email="admin2@example.com",
            nombre="Segundo Administrador",
            password_hash=default_pwd_hash,
            activo=True,
            debe_cambiar_password=False,
        )
        recepcion = Usuario(
            email="recepcion@example.com",
            nombre="Recepcionista Principal",
            password_hash=default_pwd_hash,
            activo=True,
            debe_cambiar_password=False,
        )
        mecanico = Usuario(
            email="mecanico@example.com",
            nombre="Mecánico Líder",
            password_hash=default_pwd_hash,
            activo=True,
            debe_cambiar_password=False,
        )
        mecanico2 = Usuario(
            email="mecanico2@example.com",
            nombre="Segundo Mecánico",
            password_hash=default_pwd_hash,
            activo=True,
            debe_cambiar_password=False,
        )
        cliente_user = Usuario(
            email="cliente@example.com",
            nombre="Laura Gómez",
            password_hash=default_pwd_hash,
            activo=True,
            debe_cambiar_password=False,
        )
        nuevo = Usuario(
            email="nuevo@example.com",
            nombre="Mecánico Nuevo",
            password_hash=default_pwd_hash,
            activo=True,
            debe_cambiar_password=True,
        )

        usuarios = [admin, admin2, recepcion, mecanico, mecanico2, cliente_user, nuevo]
        session.add_all(usuarios)
        await session.flush()

        # 4. Asignaciones de roles
        ahora = datetime.now(timezone.utc)
        roles = [
            AsignacionRol(usuario_id=admin.id, rol="ADMIN", desde=ahora),
            AsignacionRol(usuario_id=admin2.id, rol="ADMIN", desde=ahora),
            AsignacionRol(usuario_id=recepcion.id, rol="RECEPCION", desde=ahora),
            AsignacionRol(usuario_id=mecanico.id, rol="MECANICO", desde=ahora),
            AsignacionRol(usuario_id=mecanico2.id, rol="MECANICO", desde=ahora),
            AsignacionRol(usuario_id=cliente_user.id, rol="CLIENTE", desde=ahora),
            AsignacionRol(usuario_id=nuevo.id, rol="MECANICO", desde=ahora),
        ]
        session.add_all(roles)
        await session.flush()

        # 5. Clientes y Vehículos
        cliente_laura = Cliente(
            usuario_id=cliente_user.id,
            nombre="Laura Gómez",
            documento="30111222",
            telefono="1144556677",
        )
        cliente_jorge = Cliente(
            usuario_id=None,
            nombre="Jorge Pérez",
            documento="25333444",
            telefono="1199887766",
        )
        session.add_all([cliente_laura, cliente_jorge])
        await session.flush()

        auto_laura_1 = Vehiculo(
            cliente_id=cliente_laura.id,
            patente="AA123BB",
            marca="Toyota",
            modelo="Corolla",
            anio=2020,
        )
        auto_laura_2 = Vehiculo(
            cliente_id=cliente_laura.id,
            patente="AC456DD",
            marca="Ford",
            modelo="Focus",
            anio=2018,
        )
        auto_jorge = Vehiculo(
            cliente_id=cliente_jorge.id,
            patente="AD789EE",
            marca="Volkswagen",
            modelo="Gol",
            anio=2015,
        )
        session.add_all([auto_laura_1, auto_laura_2, auto_jorge])
        await session.flush()

        # 6. Repuestos y movimientos iniciales
        rep_filtro = Repuesto(
            codigo="REP-001",
            descripcion="Filtro de aceite",
            precio=Decimal("8500.00"),
            stock=10,
        )
        rep_pastillas = Repuesto(
            codigo="REP-002",
            descripcion="Pastillas de freno",
            precio=Decimal("15000.00"),
            stock=4,
        )
        rep_bujia = Repuesto(
            codigo="REP-003",
            descripcion="Bujía",
            precio=Decimal("3000.00"),
            stock=2,
        )
        rep_aceite = Repuesto(
            codigo="REP-004",
            descripcion="Aceite por litro",
            precio=Decimal("5000.00"),
            stock=20,
        )
        repuestos = [rep_filtro, rep_pastillas, rep_bujia, rep_aceite]
        session.add_all(repuestos)
        await session.flush()

        for rep in repuestos:
            mov = MovimientoStock(
                repuesto_id=rep.id,
                orden_id=None,
                usuario_id=admin.id,
                cantidad=rep.stock,
                motivo="Stock inicial",
                cuando=ahora,
            )
            session.add(mov)
        await session.flush()

        # 7. Órdenes de trabajo
        orden_1 = OrdenTrabajo(
            vehiculo_id=auto_laura_1.id,
            mecanico_id=None,
            estado="PENDIENTE",
            falla="Ruido extraño en el motor al arrancar en frío",
            creada_en=ahora,
            total=Decimal("0.00"),
        )
        orden_2 = OrdenTrabajo(
            vehiculo_id=auto_jorge.id,
            mecanico_id=mecanico.id,
            estado="EN_REPARACION",
            falla="Falla de encendido y tirones en baja velocidad",
            creada_en=ahora,
            total=Decimal("12000.00"),
        )
        session.add_all([orden_1, orden_2])
        await session.flush()

        item_orden_2 = ItemOrden(
            orden_id=orden_2.id,
            repuesto_id=rep_bujia.id,
            cantidad=4,
            precio_unitario=Decimal("3000.00"),
        )
        session.add(item_orden_2)

        hist_1 = HistorialEstadoOrden(
            orden_id=orden_1.id,
            desde_estado=None,
            hasta_estado="PENDIENTE",
            usuario_id=recepcion.id,
            cuando=ahora,
        )
        hist_2_init = HistorialEstadoOrden(
            orden_id=orden_2.id,
            desde_estado=None,
            hasta_estado="PENDIENTE",
            usuario_id=recepcion.id,
            cuando=ahora,
        )
        hist_2_rep = HistorialEstadoOrden(
            orden_id=orden_2.id,
            desde_estado="PENDIENTE",
            hasta_estado="EN_REPARACION",
            usuario_id=mecanico.id,
            cuando=ahora,
        )
        session.add_all([hist_1, hist_2_init, hist_2_rep])

        # 8. Historial de precio
        hist_precio = HistorialPrecioRepuesto(
            repuesto_id=rep_filtro.id,
            usuario_id=admin.id,
            precio_anterior=Decimal("8000.00"),
            precio_nuevo=Decimal("8500.00"),
            cuando=ahora,
        )
        session.add(hist_precio)

        # 9. Evento de seguridad
        evento = EventoSeguridad(
            actor="SISTEMA",
            accion="Carga de los datos iniciales",
            cuando=ahora,
        )
        session.add(evento)

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
