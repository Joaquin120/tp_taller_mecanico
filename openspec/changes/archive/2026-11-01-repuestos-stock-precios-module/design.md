# Design

## Context

Ver `proposal.md` — Why. El estado relevante:

- `app/modules/repuestos/models.py` ya define `Repuesto`, `MovimientoStock` e `HistorialPrecioRepuesto` (creados en C-02).
- `migrations/versions/001_initial_schema.py` ya crea las tablas, el índice único parcial `uq_repuesto_codigo_activo` (`codigo` WHERE `borrado_en IS NULL`), los CHECK de precio/stock y los tipos `NUMERIC(10,2)`/`timestamptz`.
- `migrations/versions/002_triggers_solo_agregado.py` ya instala `prohibir_update_delete()` y los tres triggers de sólo agregado (RN-15), incluidos `movimiento_stock` e `historial_precio_repuesto`.
- `test/solo_agregado.sql` ya contiene los 6 casos manuales de rechazo.
- El patrón de módulo está consolidado en `app/modules/usuarios/`: `repository.py` + `unit_of_work.py` + `schemas.py` + `service.py` + `router.py`, con `BaseRepository`, `SoftDeleteRepository`, `UnitOfWork`, `requiere_rol` y `armar_paginacion`.

**Por eso este change no crea migraciones.** El esquema y los triggers son preexistentes y se consumen tal cual; la tarea asociada es de verificación, no de creación.

## Goals / Non-Goals

**Goals:**
- Exponer el catálogo de repuestos con lectura para personal y mutaciones sólo para ADMIN.
- Garantizar que stock, movimientos e historial de precios cambien de forma atómica y auditable.
- Reutilizar los contratos base sin duplicar lógica de paginación, UoW ni borrado lógico.

**Non-Goals:**
- Descuento de stock por terminación de orden (pertenece a C-08).
- Búsqueda avanzada, filtros por rango de precio o categorías (no están en la KB).
- Cambiar el esquema, los triggers o el catálogo de estados.
- Exponer escrituras sobre `movimiento_stock` o `historial_precio_repuesto`.

## Decisions

### D1. Repositorios por entidad, heredando de las bases existentes
- `RepuestoRepository(SoftDeleteRepository[Repuesto])`: hereda el filtrado `borrado_en IS NULL` y `soft_delete()`; agrega `get_by_codigo_vigente(codigo)`, `listar_paginado(q, offset, limit)` y `get_para_actualizar(id)` con `with_for_update()`.
- `MovimientoStockRepository(BaseRepository[MovimientoStock])`: sólo `add()` y consultas paginadas; nunca `update()` ni `delete()`.
- `HistorialPrecioRepuestoRepository(BaseRepository[HistorialPrecioRepuesto])`: sólo `add()` y consultas paginadas.

**Por qué**: reutiliza las invariantes de C-03 y hace explícito en el tipo qué repositorios son de sólo agregado. **Alternativa descartada**: un repositorio único con métodos condicionales, que diluiría la regla de inmutabilidad.

### D2. `RepuestosUnitOfWork` compone los tres repositorios
`RepuestosUnitOfWork(UnitOfWork)` expone `self.repuestos`, `self.movimientos` y `self.precios` sobre la misma `AsyncSession`. El servicio abre `async with uow:` una vez por operación. Ningún repositorio llama a `commit()`; sólo `flush()` a través de las bases. **Alternativa descartada**: sesiones separadas por repositorio, que rompería la atomicidad de alta + movimiento y de precio + historial.

### D3. Alta con movimiento condicionado
`POST /repuestos` crea el repuesto y, si `stock_inicial > 0`, inserta `MovimientoStock(cantidad=stock_inicial, motivo="ALTA", usuario_id=actor.id, orden_id=None)`. Si `stock_inicial == 0` no se inserta movimiento, porque el CHECK `cantidad <> 0` lo prohíbe y un movimiento de cero no aporta información. **Alternativa descartada**: insertar siempre un movimiento y relajar el CHECK, lo que contradice la migración existente.

### D4. PATCH con bloqueo de fila y comparación Decimal
`PATCH /repuestos/{id}` lee el repuesto con `SELECT ... FOR UPDATE` dentro del UoW, de modo que el `precio_anterior` del historial sea el vigente y dos PATCH concurrentes no generen historiales inconsistentes. La comparación es `Decimal` exacta tras validar `decimal_places=2`; si `precio_nuevo == precio_actual` no se inserta historial (RN-20). El contrato exige al menos un campo (`descripcion` o `precio`) y prohíbe `stock` por `extra="forbid"`. **Alternativa descartada**: comparar flotantes o actualizar sin lock, que produciría historiales con precios anteriores incorrectos.

### D5. Reposición con incremento bajo lock
`POST /repuestos/{id}/reponer` bloquea la fila, valida `cantidad > 0`, aplica `stock += cantidad` e inserta el movimiento con `motivo="REPOSICION"` en el mismo UoW. **Alternativa descartada**: `UPDATE repuesto SET stock = stock + :n` suelto, que impediría auditar el movimiento en la misma transacción.

### D6. Baja lógica sin validar órdenes abiertas
`DELETE /repuestos/{id}` usa `soft_delete()`, responde 204 y libera el `codigo` por el índice parcial. A diferencia de vehículos (RN-16), la KB no exige 409 por órdenes abiertas para repuestos: la prohibición de usar repuestos dados de baja en órdenes nuevas se valida al crear la orden (C-08). **Alternativa descartada**: bloquear la baja si el repuesto está en órdenes abiertas, regla no pedida por la KB.

### D7. Historiales de sólo lectura y paginados
`GET /repuestos/{id}/movimientos` y `/precios` usan `ParamsPaginacion` + `armar_paginacion`, orden `cuando DESC, id DESC`. No hay rutas de escritura sobre estas tablas; las inserciones provienen sólo de los UoW de alta, reposición y PATCH. La inmutabilidad física ya la garantizan los triggers de la migración 002.

### D8. RBAC y montaje del router
El router del módulo se monta en `main.py` con `dependencies=[Depends(requiere_password_actualizada)]`, igual que el grupo Protegido actual. Cada endpoint declara `requiere_rol(...)` según la matriz: lectura `ADMIN`/`RECEPCION`/`MECANICO`; mutaciones e historiales `ADMIN`. **Alternativa descartada**: un router protegido aparte, que duplicaría el montaje ya existente en `main.py`.

### D9. Contratos y mapeo de errores
- `CodigoRepuesto = str` con `min_length=1, max_length=50`; `descripcion` con `min_length=1, max_length=255`.
- `precio` con `condecimal(max_digits=10, decimal_places=2, gt=0)`.
- Se extiende `_CONSTRAINT_MAP` de `main.py` con `uq_repuesto_codigo_activo` → 409, y los CHECK de repuesto/movimiento/historial → 422, para no depender del fallback genérico.
- Ningún DTO de salida incluye detalles internos ni trazas.

### D10. Fechas y dinero
- `cuando` y `borrado_en` son `DateTime(timezone=True)` (timestamptz), con `datetime.now(timezone.utc)`.
- `precio`, `precio_anterior` y `precio_nuevo` son `Numeric(10, 2)` mapeados a `Decimal`; nunca `float`.
- El redondeo a 2 decimales se valida en el contrato, no se corrige silenciosamente.

## Risks / Trade-offs

- **Doble historial por concurrencia** → mitigado con `SELECT ... FOR UPDATE` en PATCH y reposición.
- **El trigger de sólo agregado usa `ERRCODE 23505`** (definido en la migración 002), por lo que un `UPDATE`/`DELETE` directo a una tabla append-only se traduce en el fallback como 409 "El recurso ya existe" si llega al handler HTTP. No afecta a la API (no hay rutas de escritura), pero el mensaje es poco preciso para SQL manual. → Documentado; corregir el SQLSTATE exigiría otra migración, fuera de alcance.
- **Repuesto borrado en una orden ya creada** → el item conserva su `repuesto_id` y el precio copiado; la baja no rompe órdenes históricas porque es lógica. La validación de vigencia al crear órdenes queda para C-08.
- **Sin PostgreSQL disponible** → las pruebas de triggers y del índice único parcial bajo carrera no pueden ejecutarse en SQLite. Se etiquetan como verificación manual/PostgreSQL, igual que en changes anteriores.

## Migration Plan

1. No hay migraciones nuevas. Verificar que la base esté en `head` (`alembic upgrade head`) y que los triggers existan.
2. Ejecutar `test/solo_agregado.sql` contra PostgreSQL para confirmar los 6 rechazos de RN-15.
3. Rollback: al no haber migraciones, revertir el change es sólo retirar los archivos del módulo y el montaje del router.

## Open Questions

Ninguna que afecte specs, enfoque o tareas.
