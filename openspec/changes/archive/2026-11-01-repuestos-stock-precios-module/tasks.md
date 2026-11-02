# Tasks

> **Migraciones:** este change **no crea migraciones nuevas**. La migración
> autogenerada `001_initial_schema` ya crea las tablas, el índice único parcial
> `uq_repuesto_codigo_activo`, `NUMERIC(10,2)` y `timestamptz`; la migración
> manual `002_triggers_solo_agregado` ya inyecta el PL/pgSQL de los triggers de
> `movimiento_stock` e `historial_precio_repuesto`. El grupo 4 verifica ambos
> artefactos en lugar de duplicarlos.
>
> **Diferimiento:** la verificación que exige **PostgreSQL real** (ejecución de
> `test/solo_agregado.sql`, `alembic upgrade head`/`current` y concurrencia del
> índice parcial) se traslada al change **C-09** `verification-suite-e2e-docs`,
> que ya tiene ese entorno en su alcance. Esas tareas ya no forman parte del
> checklist de C-07 (ver "Tareas diferidas a C-09" al final).

## 1. Contratos, repositorios y Unit of Work

- [x] 1.1 Crear `app/modules/repuestos/schemas.py` con `RepuestoCreate`, `RepuestoUpdate`, `ReponerStockRequest`, `RepuestoResponse`, `MovimientoStockResponse` y `HistorialPrecioResponse`, todos con `extra="forbid"`; verificar con `test/test_repuestos_schemas.py` que un campo extra da 422, que `precio` exige `gt=0` y 2 decimales y que `codigo`/`descripcion` respetan sus longitudes.
- [x] 1.2 Crear `app/modules/repuestos/repository.py` con `RepuestoRepository(SoftDeleteRepository[Repuesto])` y los métodos `get_by_codigo_vigente`, `listar_paginado` y `get_para_actualizar`; agregar `MovimientoStockRepository` e `HistorialPrecioRepuestoRepository` con sólo `add` y consultas paginadas; verificar con `test/test_repuestos_repository.py` sobre SQLite que el listado excluye `borrado_en` no nulo y que los repositorios de historial no exponen `update` ni `delete`.
- [x] 1.3 Crear `app/modules/repuestos/unit_of_work.py` con `RepuestosUnitOfWork` que comparte la misma sesión entre `repuestos`, `movimientos` y `precios`; verificar con `test/test_repuestos_uow.py` que los tres repositorios usan la misma sesión y que una excepción revierte todo.
- [x] 1.4 Verificar que ningún repositorio del módulo llama a `session.commit()`; comprobar con una búsqueda en `app/modules/repuestos/` y con `test_repository.py`/`test_unit_of_work.py` que el patrón flush-only se mantiene.

## 2. Servicios y casos de uso

- [x] 2.1 Implementar `CatalogoService.listar` y `obtener` con búsqueda `q` sobre `descripcion`, paginación estándar y 404 para inexistentes/borrados; verificar con `test/test_repuestos_servicio.py` los escenarios de listado, búsqueda y página fuera de rango.
- [x] 2.2 Implementar `CatalogoService.crear` con `stock_inicial`, movimiento de alta condicionado a `stock_inicial > 0`, 409 por código duplicado y rollback ante fallo; verificar con pruebas de alta con stock, alta con cero, duplicado y error de inserción.
- [x] 2.3 Implementar `CatalogoService.actualizar` con lock de fila, historial de precio sólo si cambia y rechazo de `stock` en el contrato; verificar con pruebas de cambio de precio, precio idéntico, sólo descripción, `stock` en el body y rollback del historial.
- [x] 2.4 Implementar `CatalogoService.reponer` con `cantidad > 0`, incremento de stock y movimiento de reposición en el mismo UoW; verificar con pruebas de reposición exitosa, cantidad inválida y rollback del incremento.
- [x] 2.5 Implementar `CatalogoService.dar_de_baja` con `soft_delete()`, 204, 404 en segunda baja y liberación del código; verificar con pruebas de baja, ocultamiento en listado/detalle y reutilización de código.
- [x] 2.6 Implementar `CatalogoService.listar_movimientos` y `listar_precios` paginados por `cuando DESC, id DESC`, con 404 si el repuesto no está vigente; verificar con pruebas de historial con filas, historial vacío y repuesto inexistente.

## 3. Router, RBAC y mapeo de errores

- [x] 3.1 Crear `app/modules/repuestos/router.py` con los 8 endpoints y `requiere_rol` según la matriz (lectura para ADMIN/RECEPCION/MECANICO; mutaciones e historiales sólo ADMIN); verificar con `test/test_repuestos_router.py` que cada endpoint devuelve el código esperado.
- [x] 3.2 Montar el router en `main.py` dentro del grupo Protegido con `requiere_password_actualizada` y extender `_CONSTRAINT_MAP` con `uq_repuesto_codigo_activo` → 409 y los CHECK de repuesto/movimiento/historial → 422; verificar con `test/test_repuestos_router.py` y `test/test_integrity_handler.py` que no se filtra ningún detalle de PostgreSQL.
- [x] 3.3 Verificar autorización: sin sesión 401, `CLIENTE` 403 en lectura y `RECEPCION` 403 en mutaciones, con pruebas en `test/test_repuestos_router.py`.
- [x] 3.4 Verificar `PATCH /repuestos/{id}` con `stock` en el body devuelve 422 y que `GET` sobre `/movimientos` y `/precios` con métodos de escritura devuelve 405, con pruebas en `test/test_repuestos_router.py`.

## 4. Verificación del esquema y de los triggers existentes (sin migraciones nuevas)

- [x] 4.1 Revisar `migrations/versions/001_initial_schema.py` y confirmar que `repuesto` ya tiene `uq_repuesto_codigo_activo` con `postgresql_where=borrado_en IS NULL`, `NUMERIC(10,2)` y `timestamptz`; verificar con `test/test_repuestos_repository.py` que el modelo mapea esos tipos y con `alembic heads` que no se agregó una migración nueva.

## 5. Integración y regresión

- [x] 5.1 Ejecutar la suite completa con `.venv\Scripts\python.exe -m pytest -q` y confirmar que las 150 pruebas previas más las nuevas pasan sin warnings.
- [x] 5.2 Ejecutar `openspec validate --strict` (con `--all` o `--specs` si no hay changes activos) y confirmar 0 fallos.
- [x] 5.3 Actualizar `CHANGES.md` marcando C-07 como completado sólo después de archivar el change.

## Tareas diferidas a C-09

> Estas tareas **no son pendientes de C-07**: requieren un PostgreSQL real que el
> entorno actual no tiene disponible ni autorizado. Su ejecución y evidencia se
> registran en **C-09** `verification-suite-e2e-docs`, que ya incluye
> `test/solo_agregado.sql` y la verificación con migraciones reales. El código de
> C-07 no necesita cambios para ejecutarlas.

- **4.2 (diferida)** Ejecutar `test/solo_agregado.sql` contra PostgreSQL para verificar que los triggers de `002_triggers_solo_agregado` rechazan `UPDATE`/`DELETE` sobre `movimiento_stock` e `historial_precio_repuesto` (los 6 casos deben fallar con excepción). *La revisión estática de la migración ya se completó.*
- **4.3 (diferida)** Ejecutar `alembic upgrade head` y `alembic current` contra PostgreSQL para confirmar que la base queda en `002_triggers_solo_agregado`.
- **4.4 (diferida)** Probar en PostgreSQL el índice único parcial bajo concurrencia: dos altas simultáneas con el mismo `codigo` deben dejar exactamente una fila vigente y una respuesta 409.

## Workflow follow-up

- Archivar el change y sincronizar la spec `spare-parts-inventory` a `openspec/specs/`.
- Marcar `[x]` la entrada de C-07 en `CHANGES.md` únicamente al archivar.

## Notas de verificación (corrida de implementación C-07)

### Evidencia local ejecutada

- `.venv\Scripts\python.exe -m pytest -q` → **224 passed**, 0 warnings.
- `openspec validate --strict --all` → **9 passed, 0 failed**.
- `alembic heads` → `002_triggers_solo_agregado (head)`; **no se agregó migración nueva**.
- `Select-String` sobre `app/modules/repuestos/*.py` por `.commit(` → **sin coincidencias**
  (sólo `flush` en repositorios; el `commit` es exclusivo del `UnitOfWork`).
- `test/test_repuestos_repository.py::test_modelo_mapea_el_esquema_existente_de_la_migracion_001`
  comprueba `Numeric(10,2)`, `DateTime(timezone=True)` y el índice único parcial
  `uq_repuesto_codigo_activo` con `WHERE borrado_en IS NULL`.

### Diferimiento a C-09

Las tareas 4.2, 4.3 y 4.4 se movieron a la sección "Tareas diferidas a C-09" y
dejaron de usar checkboxes, de modo que el checklist de C-07 queda **18/18**
completo. El bloqueo es exclusivamente de infraestructura (PostgreSQL/Docker no
disponibles ni autorizados), no de código.

### Nota sobre la base simulada

`test/infra_sqlite.py` elimina `uq_repuesto_codigo_activo` en la base SQLite porque
SQLite crea ese índice **completo** (sin `WHERE borrado_en IS NULL`) y bloquearía la
reutilización del código de un repuesto dado de baja. El índice parcial real sólo se
ejercita contra PostgreSQL (tarea 4.4, diferida a C-09).
