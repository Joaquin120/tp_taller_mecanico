from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import SQLModel

from app.modules.usuarios.models import Usuario, AsignacionRol, IntentoAcceso, EventoSeguridad
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.repuestos.models import Repuesto, MovimientoStock, HistorialPrecioRepuesto
from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo, ItemOrden, HistorialEstadoOrden


def test_declarative_tables_registered():
    table_names = SQLModel.metadata.tables.keys()
    expected_tables = {
        "usuario",
        "asignacion_rol",
        "intento_acceso",
        "evento_seguridad",
        "cliente",
        "vehiculo",
        "repuesto",
        "movimiento_stock",
        "historial_precio_repuesto",
        "estado_orden",
        "orden_trabajo",
        "item_orden",
        "historial_estado_orden",
    }
    assert expected_tables.issubset(table_names)


def test_usuario_and_cliente_relationship():
    # Verificar uselist=False en relacion 1-a-1 Usuario.cliente
    usuario_cliente_rel = Usuario.__sqlmodel_relationships__["cliente"]
    assert usuario_cliente_rel.sa_relationship_kwargs.get("uselist") is False

    # Instanciación básica de Usuario
    user = Usuario(
        email="test@example.com",
        nombre="Test User",
        password_hash="hashed_pw",
        activo=True,
    )
    assert user.email == "test@example.com"
    assert user.debe_cambiar_password is False


def test_asignacion_rol_constraints_and_partial_index():
    table = SQLModel.metadata.tables["asignacion_rol"]
    check_names = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert "ck_asignacion_rol_rol_valido" in check_names

    index_names = [idx.name for idx in table.indexes]
    assert "uq_asignacion_rol_activa" in index_names

    partial_idx = next(idx for idx in table.indexes if idx.name == "uq_asignacion_rol_activa")
    assert partial_idx.unique is True
    assert "revocada_en IS NULL" in str(partial_idx.dialect_options["postgresql"]["where"])


def test_vehiculo_constraints_and_partial_index():
    table = SQLModel.metadata.tables["vehiculo"]
    check_names = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert "ck_vehiculo_anio_valido" in check_names

    index_names = [idx.name for idx in table.indexes]
    assert "uq_vehiculo_patente_activa" in index_names

    partial_idx = next(idx for idx in table.indexes if idx.name == "uq_vehiculo_patente_activa")
    assert partial_idx.unique is True
    assert "borrado_en IS NULL" in str(partial_idx.dialect_options["postgresql"]["where"])


def test_repuesto_constraints_and_partial_index():
    table = SQLModel.metadata.tables["repuesto"]
    check_names = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert "ck_repuesto_precio_positivo" in check_names
    assert "ck_repuesto_stock_no_negativo" in check_names

    index_names = [idx.name for idx in table.indexes]
    assert "uq_repuesto_codigo_activo" in index_names

    partial_idx = next(idx for idx in table.indexes if idx.name == "uq_repuesto_codigo_activo")
    assert partial_idx.unique is True
    assert "borrado_en IS NULL" in str(partial_idx.dialect_options["postgresql"]["where"])


def test_item_orden_constraints_and_uniqueness():
    table = SQLModel.metadata.tables["item_orden"]
    check_names = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert "ck_item_orden_cantidad_positiva" in check_names
    assert "ck_item_orden_precio_positivo" in check_names

    unique_names = [c.name for c in table.constraints if isinstance(c, UniqueConstraint)]
    assert "uq_item_orden_orden_repuesto" in unique_names


def test_estado_orden_catalog_primary_key():
    table = SQLModel.metadata.tables["estado_orden"]
    pk_cols = [col.name for col in table.primary_key.columns]
    assert pk_cols == ["codigo"]


def test_historial_precio_repuesto_constraints():
    table = SQLModel.metadata.tables["historial_precio_repuesto"]
    check_names = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert "ck_historial_precio_nuevo_positivo" in check_names
    assert "ck_historial_precio_cambio_requerido" in check_names


def test_movimiento_stock_constraints():
    table = SQLModel.metadata.tables["movimiento_stock"]
    check_names = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert "ck_movimiento_stock_cantidad_no_cero" in check_names


def test_orden_trabajo_constraints():
    table = SQLModel.metadata.tables["orden_trabajo"]
    check_names = [c.name for c in table.constraints if isinstance(c, CheckConstraint)]
    assert "ck_orden_trabajo_total_no_negativo" in check_names
