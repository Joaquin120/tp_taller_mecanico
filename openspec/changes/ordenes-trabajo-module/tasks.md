# Tasks

> **Punto de partida:** `app/modules/ordenes/models.py` y las cuatro tablas ya existen desde C-02, y `app/modules/ordenes/repository.py` ya está en el árbol como dependencia de C-06. Las tareas de modelos y migraciones **crean/auditan** y completan esos artefactos; no se parte de cero ni se duplican tablas.

## 1. Modelos y migraciones

- [ ] 1.1 Auditar y completar el modelo `EstadoOrden` (`codigo` PK, `descripcion`, `posicion` único, `es_final`) y verificar con `test/test_ordenes_modelos.py` que el mapeo reproduce la tabla `estado_orden` de `001_initial_schema` (tipo, PK y unique de `posicion`).
- [ ] 1.2 Auditar y completar el modelo `OrdenTrabajo` (FK `vehiculo_id`, FK opcional `mecanico_id`, FK `estado`, `falla` 500, `creada_en` timestamptz, `total` `Numeric(12,2)` con CHECK `>= 0`, relaciones `vehiculo`/`mecanico`/`estado_rel`/`items`/`historial_estados`/`movimientos_stock`) y verificar con `test/test_ordenes_modelos.py` el tipo `Numeric(12,2)`, el CHECK y las FK.
- [ ] 1.3 Auditar y completar el modelo `ItemOrden` (FK `orden_id`, FK `repuesto_id`, `cantidad > 0`, `precio_unitario Numeric(10,2) > 0`, `UNIQUE(orden_id, repuesto_id)`) y verificar con `test/test_ordenes_modelos.py` las dos CHECK y la restricción única.
- [ ] 1.4 Auditar y completar el modelo `HistorialEstadoOrden` (`desde_estado` opcional, `hasta_estado` obligatorio, `usuario_id`, `cuando` timestamptz, relaciones con `OrdenTrabajo` y con ambos estados mediante `foreign_keys`) y verificar con `test/test_ordenes_modelos.py` que inserta `desde_estado=NULL` y que el mapeo de las dos FK a `estado_orden.codigo` no se cruza.
- [ ] 1.5 Generar la migración autogenerada `migrations/versions/003_ordenes_schema_sync.py` con `alembic revision --autogenerate -m "ordenes schema sync"`; revisar que no introduzca drift respecto de los modelos y, si el autogenerate sale vacío, dejarla documentada como no-op explícita. Verificar con `alembic heads` que `003_ordenes_schema_sync` es la cabeza y que `alembic upgrade head` no falla.
- [ ] 1.6 Crear la migración manual `migrations/versions/004_ordenes_triggers_y_fk.py` con guardas idempotentes: FK `movimiento_stock.orden_id → orden_trabajo.id` y su índice si faltaran (`DO $$ ... IF NOT EXISTS` sobre `pg_constraint`/`pg_indexes`), y `CREATE OR REPLACE` de `prohibir_update_delete()` más el trigger de sólo agregado de `historial_estado_orden`. Verificar con `alembic upgrade head`/`alembic current` que la base queda en `004` y con una revisión estática del archivo que no duplica triggers en bases ya migradas.
- [ ] 1.7 Confirmar que `seed.py` siembra `PENDIENTE`, `EN_REPARACION`, `TERMINADA` y `CANCELADA` con `posicion` y `es_final` correctos; verificar con una prueba que inserta las filas de `seed` en SQLite y consulta el catálogo ordenado.

## 2. Contratos Pydantic

- [ ] 2.1 Crear `app/modules/ordenes/schemas.py` con `ItemOrdenRequest` (`repuesto_id`, `cantidad > 0`), `OrdenCrearRequest` (`vehiculo_id`, `falla` 1..500, `items` con `min_length=1`) y `EstadoOrdenResponse`; todos con `extra="forbid"`. Verificar con `test/test_ordenes_schemas.py` que `precio_unitario`, `subtotal`, `total`, `estado` y `mecanico_id` en el payload dan 422 y que `items: []`, `falla` vacía o `cantidad <= 0` también dan 422.
- [ ] 2.2 Agregar los contratos de salida `ItemOrdenResponse` (con `subtotal` calculado), `HistorialEstadoResponse`, `OrdenResponse` (patente, cliente, items, historial, total `Decimal`) y `OrdenResumenResponse`. Verificar con `test/test_ordenes_schemas.py` que no exponen campos internos ni permiten campos extra y que serializan `Decimal` y `datetime` con zona horaria.

## 3. Repositorios y Unit of Work

- [ ] 3.1 Implementar `EstadoOrdenRepository` de sólo lectura en `app/modules/ordenes/repository.py` (`listar_por_posicion`, `get_by_codigo`, `contar`), sin heredar de `BaseRepository` y sin `add`/`update`/`delete`. Verificar con `test/test_ordenes_repository.py` que el catálogo se ordena por `posicion` y que el repositorio no expone métodos de escritura.
- [ ] 3.2 Completar `OrdenTrabajoRepository` con `get_detalle` (carga anticipada `vehiculo → cliente`, `items → repuesto`, `historial_estados`, `mecanico`), `get_para_actualizar`, `listar`, `contar_por_estado`, `listar_por_cliente_usuario` y `contar_por_cliente_usuario`. Verificar con `test/test_ordenes_repository.py` que el detalle trae todas las relaciones, que el filtro por cliente sólo devuelve órdenes propias y que la paginación y el orden por `id DESC` se respetan.
- [ ] 3.3 Completar `ItemOrdenRepository` (`listar_por_orden`) y `HistorialEstadoOrdenRepository` como repositorio de **sólo agregado**: expone `add` y `listar_por_orden`, y `update`/`delete` lanzan `NotImplementedError`. Verificar con `test/test_ordenes_repository.py` que un `update` o `delete` sobre el historial falla explícitamente.
- [ ] 3.4 Crear `app/modules/ordenes/unit_of_work.py` con `OrdenesUnitOfWork` que compone `estados`, `ordenes`, `items`, `historial`, `vehiculos` (C-06), `repuestos` y `movimientos` (C-07) sobre la **misma sesión**. Verificar con `test/test_ordenes_uow.py` que los siete repositorios comparten sesión, que una excepción revierte todo y que ningún repositorio del módulo llama a `session.commit()` (búsqueda en `app/modules/ordenes/` y ejecución de la suite).
- [ ] 3.5 Exponer en `MovimientoStockRepository` (C-07) sólo lo necesario para órdenes (inserción y consulta ya existentes) sin relajar la inmutabilidad; si hiciera falta un método nuevo, agregarlo sin `update`/`delete`. Verificar con `test/test_ordenes_repository.py` que el repositorio de movimientos sigue rechazando `update`/`delete`.

## 4. Servicios y casos de uso atómicos

- [ ] 4.1 Implementar `OrdenService.listar_estados` y `crear_orden`: valida catálogo con `PENDIENTE` (409 si falta), vehículo vigente (409), ítems no vacíos/no repetidos (422), copia `precio_unitario` vigente, calcula `subtotal`/`total` con `Decimal`, crea la orden en `PENDIENTE`, sus ítems y la primera línea de historial en un único UoW. Verificar con `test/test_ordenes_servicio.py` los escenarios de alta, total calculado, catálogo vacío, vehículo inválido, repuesto inválido, ítems repetidos y rollback ante fallo de inserción.
- [ ] 4.2 Implementar `listar_ordenes`, `obtener_orden` y `listar_mis_ordenes`: paginación estándar, filtro por estado, detalle con autorización (personal o cliente dueño, 403 en caso contrario) y `/mis-ordenes` filtrado por `Cliente.usuario_id`. Verificar con `test/test_ordenes_servicio.py` el listado, el filtro, la página fuera de rango, el detalle propio/ajeno y la lista vacía de un cliente sin órdenes.
- [ ] 4.3 Implementar `iniciar_orden`: exige `PENDIENTE`, autoasigna `mecanico_id` al actor e inserta historial `PENDIENTE → EN_REPARACION`; devuelve 409 si el estado no lo permite y 403 si el actor no es `MECANICO` (validado en router). Verificar con `test/test_ordenes_servicio.py` los dos caminos y que no se modifica ninguna orden ajena al estado esperado.
- [ ] 4.4 Implementar `terminar_orden` atómico: autoriza mecánico asignado o `ADMIN`, exige `EN_REPARACION`, bloquea la orden y los repuestos en orden ascendente de `repuesto_id`, valida **todos** los stocks antes de escribir, descuenta stock, inserta un `movimiento_stock` negativo por ítem con `orden_id`, pasa a `TERMINADA` e inserta historial. Verificar con `test/test_ordenes_servicio.py` la terminación exitosa, el stock insuficiente con **rollback total** (stock, movimientos, estado e historial intactos), la orden no iniciada y el actor no autorizado.
- [ ] 4.5 Implementar `cancelar_orden` evaluando **primero** permisos (ADMIN, RECEPCION o cliente dueño) y **después** el estado `PENDIENTE`: 403 antes que 409 cuando falta permiso y 409 cuando el estado no permite cancelar. Verificar con `test/test_ordenes_servicio.py` la cancelación por dueño, por recepción, el cliente ajeno sobre una orden `TERMINADA` (403), el actor autorizado sobre una orden `EN_REPARACION` (409) y la orden inexistente (404).
- [ ] 4.6 Implementar el aviso simulado `avisar_cliente_simulado(orden_id, destinatario)` con `asyncio.sleep(0.5)` y log, y agendarlo desde el router con `BackgroundTasks` sólo después del retorno exitoso del servicio. Verificar con `test/test_ordenes_router.py` que se agenda y ejecuta tras un 200, que no se agenda tras un 409 y que un fallo del aviso no altera la respuesta.

## 5. Router, RBAC y mapeo de errores

- [ ] 5.1 Crear `app/modules/ordenes/router.py` con `GET /estados-orden`, `POST /ordenes`, `GET /ordenes`, `GET /ordenes/{id}`, `POST /ordenes/{id}/iniciar`, `POST /ordenes/{id}/terminar`, `POST /ordenes/{id}/cancelar` y `GET /mis-ordenes`, con `requiere_rol`/`get_current_user` según la matriz y un `get_ordenes_uow` que construye el UoW con la sesión de la dependencia. Verificar con `test/test_ordenes_router.py` el código de estado de cada endpoint.
- [ ] 5.2 Montar el router en el grupo Protegido de `main.py` con `requiere_password_actualizada`, junto a clientes y repuestos, y ampliar `_CONSTRAINT_MAP` con `uq_item_orden_orden_repuesto`, `ck_item_orden_cantidad_positiva`, `ck_item_orden_precio_positivo`, `ck_orden_trabajo_total_no_negativo` y las FK de orden/ítem. Verificar con `test/test_ordenes_router.py` y `test/test_integrity_handler.py` que no se filtra ningún detalle de PostgreSQL.
- [ ] 5.3 Verificar autorización completa: sin sesión 401 en todos los endpoints, `CLIENTE` 403 en `POST /ordenes`, `ADMIN`/`RECEPCION` 403 en `iniciar`, mecánico no asignado 403 en `terminar`, `MECANICO` 403 en `cancelar` y cliente ajeno 403 en detalle y `mis-ordenes` sin datos de terceros, con pruebas en `test/test_ordenes_router.py`.
- [ ] 5.4 Verificar que `POST /estados-orden`, `PATCH` y `DELETE` sobre el catálogo responden 404/405 y que ningún método de escritura existe para el historial de estados, con pruebas en `test/test_ordenes_router.py`.
- [ ] 5.5 Verificar que el payload con `precio_unitario`, `subtotal`, `total`, `estado` o `mecanico_id` responde 422 en `POST /ordenes` y que `falla` fuera de 1..500 responde 422, con pruebas en `test/test_ordenes_router.py`.

## 6. Integración y regresión

- [ ] 6.1 Ejecutar la suite completa con `.venv\Scripts\python.exe -m pytest -q` y confirmar que las 252 pruebas previas (C-07 + C-06) más las nuevas pasan sin warnings.
- [ ] 6.2 Verificar el detalle sin N+1 comparando el número de sentencias SQL de una orden con 2 y con 4 ítems (mismo número), con una prueba en `test/test_ordenes_servicio.py` que instrumente el engine o use `SQL_ECHO`.
- [ ] 6.3 Ejecutar `openspec validate ordenes-trabajo-module --strict` y luego `openspec validate --all --strict`; confirmar 0 fallos y que `openspec status --change ordenes-trabajo-module` reporta todos los artefactos `done`.
- [ ] 6.4 Actualizar `CHANGES.md` marcando C-08 como completado **sólo después de archivar** el change, y registrar en `tasks.md` la evidencia de los comandos ejecutados.

## Tareas diferidas a C-09

> Requieren PostgreSQL real o infraestructura que el entorno actual no tiene disponible ni autorizada. No forman parte del checklist de C-08 y no se marcan como pendientes.

- **Verificación de triggers**: ejecutar `test/solo_agregado.sql` contra PostgreSQL para comprobar que el trigger de `historial_estado_orden` (y los de C-07) rechazan `UPDATE`/`DELETE`.
- **Migraciones reales**: `alembic upgrade head`/`alembic current` contra PostgreSQL para confirmar que la base queda en `004_ordenes_triggers_y_fk` y que las guardas de la 004 no duplican FK ni triggers.
- **Concurrencia**: dos terminaciones simultáneas de la misma orden deben descontar stock una sola vez, y dos altas concurrentes con el mismo código de repuesto deben dejar una sola fila vigente.
- **Suite `.http`**: C-10 a C-13 del enunciado, incluida la verificación de N+1 con `SQL_ECHO=true` sobre la aplicación real.

## Workflow follow-up

- Archivar el change y sincronizar la spec `work-order-lifecycle` a `openspec/specs/`.
- Marcar `[x]` la entrada de C-08 en `CHANGES.md` únicamente al archivar.
