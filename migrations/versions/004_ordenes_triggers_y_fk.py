"""004_ordenes_triggers_y_fk

Guardas idempotentes de esquema para el módulo de órdenes (C-08).

Aunque `001_initial_schema` ya crea la FK `movimiento_stock.orden_id` y
`002_triggers_solo_agregado` ya instala el trigger de `historial_estado_orden`,
esta migración manual deja ambos artefactos garantizados en bases que se
desplegaron antes de esas revisiones o que fueron reparadas a mano. Todas las
operaciones son idempotentes y no duplican objetos.

No modifica tipos, columnas ni tablas: sólo verifica/crea la FK, su índice y
el disparador de sólo agregado (RN-15, RN-19).

Revision ID: 004_ordenes_triggers_y_fk
Revises: 003_ordenes_schema_sync
Create Date: 2026-11-01 12:05:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "004_ordenes_triggers_y_fk"
down_revision: Union[str, None] = "003_ordenes_schema_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. FK movimiento_stock.orden_id -> orden_trabajo.id (si faltara)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'movimiento_stock_orden_id_fkey'
                  AND conrelid = 'movimiento_stock'::regclass
            ) THEN
                ALTER TABLE movimiento_stock
                    ADD CONSTRAINT movimiento_stock_orden_id_fkey
                    FOREIGN KEY (orden_id) REFERENCES orden_trabajo(id);
            END IF;
        END
        $$;
        """
    )

    # 2. Índice de apoyo para la FK (si faltara)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_movimiento_stock_orden_id "
        "ON movimiento_stock (orden_id);"
    )

    # 3. Función PL/pgSQL de sólo agregado (ya definida por 002: se reemplaza)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prohibir_update_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Operación % no permitida en tabla de sólo agregado %', TG_OP, TG_TABLE_NAME
                USING ERRCODE = '23505';
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # 4. Trigger de historial_estado_orden (si faltara en una base reparada)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_trigger
                WHERE tgname = 'trg_solo_agregado_historial_estado_orden'
                  AND tgrelid = 'historial_estado_orden'::regclass
            ) THEN
                EXECUTE 'CREATE TRIGGER trg_solo_agregado_historial_estado_orden '
                        'BEFORE UPDATE OR DELETE ON historial_estado_orden '
                        'FOR EACH ROW EXECUTE FUNCTION prohibir_update_delete()';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """No destructivo a propósito.

    La FK y el trigger pertenecen a `001_initial_schema` y
    `002_triggers_solo_agregado`; eliminarlos acá rompería C-07 y la
    inmutabilidad de la auditoría. Esta revisión sólo garantiza su existencia,
    por lo que revertirla no debe borrar objetos preexistentes.
    """
