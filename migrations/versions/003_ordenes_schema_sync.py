"""003_ordenes_schema_sync

Sincronización de esquema del módulo de órdenes de trabajo (C-08).

Las cuatro tablas (`estado_orden`, `orden_trabajo`, `item_orden`,
`historial_estado_orden`) ya fueron creadas por `001_initial_schema` (C-02).
Esta revisión es el resultado de la comprobación de drift entre los modelos
SQLModel de `app/modules/ordenes/models.py` y esa migración:

- `estado_orden`: PK `codigo`, `posicion` único y `es_final` booleano.
- `orden_trabajo`: `total NUMERIC(12,2)` con CHECK `>= 0`, `creada_en`
  timestamptz y FK a `vehiculo`, `usuario` y `estado_orden`.
- `item_orden`: `cantidad > 0`, `precio_unitario NUMERIC(10,2) > 0` y
  `UNIQUE (orden_id, repuesto_id)`.
- `historial_estado_orden`: `desde_estado` opcional, `hasta_estado`
  obligatorio, `usuario_id` y `cuando` timestamptz.

No hay drift: la revisión queda como no-op explícita. `alembic autogenerate`
requiere una conexión real a PostgreSQL, que este entorno no tiene disponible
ni autorizada (igual que en C-07); por eso la comprobación se hizo comparando
los modelos y `001_initial_schema` campo por campo. La verificación con
PostgreSQL real está diferida a C-09.

Revision ID: 003_ordenes_schema_sync
Revises: 002_triggers_solo_agregado
Create Date: 2026-11-01 12:00:00.000000
"""

from typing import Sequence, Union

revision: str = "003_ordenes_schema_sync"
down_revision: Union[str, None] = "002_triggers_solo_agregado"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Sin operaciones: los modelos ya coinciden con la migración 001."""


def downgrade() -> None:
    """Sin operaciones: no se creó ningún objeto de esquema."""
