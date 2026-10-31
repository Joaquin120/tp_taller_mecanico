"""
001_initial_schema

Esquema inicial relacional con las 13 entidades del sistema de taller mecánico.
Incluye claves primarias, claves foráneas, restricciones CHECK de dominio e
índices únicos parciales para soporte de borrado lógico y asignaciones de rol vigentes.
Revisada manualmente antes de su aplicación según consigna del TP.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-31 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. usuario
    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("debe_cambiar_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("password_cambiada_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_usuario_email"), "usuario", ["email"], unique=True)

    # 2. asignacion_rol
    op.create_table(
        "asignacion_rol",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("rol", sa.String(length=50), nullable=False),
        sa.Column("desde", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("vence_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otorgada_por", sa.Integer(), nullable=True),
        sa.CheckConstraint("rol IN ('ADMIN', 'RECEPCION', 'MECANICO', 'CLIENTE')", name="ck_asignacion_rol_rol_valido"),
        sa.ForeignKeyConstraint(["otorgada_por"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_asignacion_rol_usuario_id"), "asignacion_rol", ["usuario_id"], unique=False)
    op.create_index(
        "uq_asignacion_rol_activa",
        "asignacion_rol",
        ["usuario_id", "rol"],
        unique=True,
        postgresql_where=sa.text("revocada_en IS NULL"),
    )

    # 3. intento_acceso
    op.create_table(
        "intento_acceso",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("cuando", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("ip", sa.String(length=50), nullable=False),
        sa.Column("exito", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intento_acceso_email_ip_cuando", "intento_acceso", ["email", "ip", "cuando"], unique=False)

    # 4. evento_seguridad
    op.create_table(
        "evento_seguridad",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("cuando", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("accion", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 5. cliente
    op.create_table(
        "cliente",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("documento", sa.String(length=50), nullable=False),
        sa.Column("telefono", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("documento"),
        sa.UniqueConstraint("usuario_id"),
    )
    op.create_index(op.f("ix_cliente_documento"), "cliente", ["documento"], unique=True)

    # 6. vehiculo
    op.create_table(
        "vehiculo",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("patente", sa.String(length=20), nullable=False),
        sa.Column("marca", sa.String(length=100), nullable=False),
        sa.Column("modelo", sa.String(length=100), nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("borrado_en", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("anio BETWEEN 1950 AND 2100", name="ck_vehiculo_anio_valido"),
        sa.ForeignKeyConstraint(["cliente_id"], ["cliente.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vehiculo_cliente_id"), "vehiculo", ["cliente_id"], unique=False)
    op.create_index(
        "uq_vehiculo_patente_activa",
        "vehiculo",
        ["patente"],
        unique=True,
        postgresql_where=sa.text("borrado_en IS NULL"),
    )

    # 7. repuesto
    op.create_table(
        "repuesto",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=False),
        sa.Column("precio", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("borrado_en", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("precio > 0", name="ck_repuesto_precio_positivo"),
        sa.CheckConstraint("stock >= 0", name="ck_repuesto_stock_no_negativo"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_repuesto_codigo_activo",
        "repuesto",
        ["codigo"],
        unique=True,
        postgresql_where=sa.text("borrado_en IS NULL"),
    )

    # 8. estado_orden
    op.create_table(
        "estado_orden",
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=False),
        sa.Column("posicion", sa.Integer(), nullable=False),
        sa.Column("es_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("codigo"),
        sa.UniqueConstraint("posicion"),
    )

    # 9. orden_trabajo
    op.create_table(
        "orden_trabajo",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("vehiculo_id", sa.Integer(), nullable=False),
        sa.Column("mecanico_id", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(length=50), nullable=False),
        sa.Column("falla", sa.String(length=500), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0.00")),
        sa.CheckConstraint("total >= 0", name="ck_orden_trabajo_total_no_negativo"),
        sa.ForeignKeyConstraint(["estado"], ["estado_orden.codigo"]),
        sa.ForeignKeyConstraint(["mecanico_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["vehiculo_id"], ["vehiculo.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orden_trabajo_estado"), "orden_trabajo", ["estado"], unique=False)
    op.create_index(op.f("ix_orden_trabajo_mecanico_id"), "orden_trabajo", ["mecanico_id"], unique=False)
    op.create_index(op.f("ix_orden_trabajo_vehiculo_id"), "orden_trabajo", ["vehiculo_id"], unique=False)

    # 10. item_orden
    op.create_table(
        "item_orden",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("orden_id", sa.Integer(), nullable=False),
        sa.Column("repuesto_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.CheckConstraint("cantidad > 0", name="ck_item_orden_cantidad_positiva"),
        sa.CheckConstraint("precio_unitario > 0", name="ck_item_orden_precio_positivo"),
        sa.ForeignKeyConstraint(["orden_id"], ["orden_trabajo.id"]),
        sa.ForeignKeyConstraint(["repuesto_id"], ["repuesto.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("orden_id", "repuesto_id", name="uq_item_orden_orden_repuesto"),
    )
    op.create_index(op.f("ix_item_orden_orden_id"), "item_orden", ["orden_id"], unique=False)
    op.create_index(op.f("ix_item_orden_repuesto_id"), "item_orden", ["repuesto_id"], unique=False)

    # 11. historial_estado_orden
    op.create_table(
        "historial_estado_orden",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("orden_id", sa.Integer(), nullable=False),
        sa.Column("desde_estado", sa.String(length=50), nullable=True),
        sa.Column("hasta_estado", sa.String(length=50), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("cuando", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["desde_estado"], ["estado_orden.codigo"]),
        sa.ForeignKeyConstraint(["hasta_estado"], ["estado_orden.codigo"]),
        sa.ForeignKeyConstraint(["orden_id"], ["orden_trabajo.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_historial_estado_orden_orden_id"), "historial_estado_orden", ["orden_id"], unique=False)

    # 12. movimiento_stock
    op.create_table(
        "movimiento_stock",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("repuesto_id", sa.Integer(), nullable=False),
        sa.Column("orden_id", sa.Integer(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(length=255), nullable=False),
        sa.Column("cuando", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("cantidad <> 0", name="ck_movimiento_stock_cantidad_no_cero"),
        sa.ForeignKeyConstraint(["orden_id"], ["orden_trabajo.id"]),
        sa.ForeignKeyConstraint(["repuesto_id"], ["repuesto.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_movimiento_stock_orden_id"), "movimiento_stock", ["orden_id"], unique=False)
    op.create_index(op.f("ix_movimiento_stock_repuesto_id"), "movimiento_stock", ["repuesto_id"], unique=False)

    # 13. historial_precio_repuesto
    op.create_table(
        "historial_precio_repuesto",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("repuesto_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("precio_anterior", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("precio_nuevo", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("cuando", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("precio_nuevo > 0", name="ck_historial_precio_nuevo_positivo"),
        sa.CheckConstraint("precio_nuevo <> precio_anterior", name="ck_historial_precio_cambio_requerido"),
        sa.ForeignKeyConstraint(["repuesto_id"], ["repuesto.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_historial_precio_repuesto_repuesto_id"), "historial_precio_repuesto", ["repuesto_id"], unique=False)


def downgrade() -> None:
    op.drop_table("historial_precio_repuesto")
    op.drop_table("movimiento_stock")
    op.drop_table("historial_estado_orden")
    op.drop_table("item_orden")
    op.drop_table("orden_trabajo")
    op.drop_table("estado_orden")
    op.drop_table("repuesto")
    op.drop_table("vehiculo")
    op.drop_table("cliente")
    op.drop_table("evento_seguridad")
    op.drop_table("intento_acceso")
    op.drop_table("asignacion_rol")
    op.drop_table("usuario")
