"""
002_triggers_solo_agregado

Disparadores PL/pgSQL de base de datos para tablas de sólo agregado (RN-15).
Prohíbe cualquier operación de UPDATE o DELETE sobre historial_estado_orden,
movimiento_stock e historial_precio_repuesto, garantizando la inmutabilidad de la auditoría.
Escrita y revisada manualmente según consigna del TP (Alembic autogenerate no detecta disparadores).

Revision ID: 002_triggers_solo_agregado
Revises: 001_initial_schema
Create Date: 2026-10-31 00:05:00.000000
"""

from typing import Sequence, Union
from alembic import op

revision: str = "002_triggers_solo_agregado"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Función PL/pgSQL que rechaza UPDATE y DELETE
    op.execute("""
        CREATE OR REPLACE FUNCTION prohibir_update_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Operación % no permitida en tabla de sólo agregado %', TG_OP, TG_TABLE_NAME
                USING ERRCODE = '23505';
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 2. Trigger en historial_estado_orden
    op.execute("""
        CREATE TRIGGER trg_solo_agregado_historial_estado_orden
        BEFORE UPDATE OR DELETE ON historial_estado_orden
        FOR EACH ROW
        EXECUTE FUNCTION prohibir_update_delete();
    """)

    # 3. Trigger en movimiento_stock
    op.execute("""
        CREATE TRIGGER trg_solo_agregado_movimiento_stock
        BEFORE UPDATE OR DELETE ON movimiento_stock
        FOR EACH ROW
        EXECUTE FUNCTION prohibir_update_delete();
    """)

    # 4. Trigger en historial_precio_repuesto
    op.execute("""
        CREATE TRIGGER trg_solo_agregado_historial_precio_repuesto
        BEFORE UPDATE OR DELETE ON historial_precio_repuesto
        FOR EACH ROW
        EXECUTE FUNCTION prohibir_update_delete();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_solo_agregado_historial_precio_repuesto ON historial_precio_repuesto;")
    op.execute("DROP TRIGGER IF EXISTS trg_solo_agregado_movimiento_stock ON movimiento_stock;")
    op.execute("DROP TRIGGER IF EXISTS trg_solo_agregado_historial_estado_orden ON historial_estado_orden;")
    op.execute("DROP FUNCTION IF EXISTS prohibir_update_delete();")
