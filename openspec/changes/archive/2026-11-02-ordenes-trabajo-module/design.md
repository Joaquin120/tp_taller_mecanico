# Design

## Context

Ver `proposal.md` — Why. Estado actual que condiciona el enfoque:

- `app/modules/ordenes/models.py` ya define `EstadoOrden`, `OrdenTrabajo`, `ItemOrden` e `HistorialEstadoOrden` (creados en C-02), con `Numeric(12,2)`/`Numeric(10,2)`, `timestamptz`, CHECK de total/cantidad/precio y `UNIQUE(orden_id, repuesto_id)`.
- `migrations/versions/001_initial_schema.py` crea las cuatro tablas y **ya incluye** la FK `movimiento_stock.orden_id → orden_trabajo.id` con su índice `ix_movimiento_stock_orden_id`.
- `migrations/versions/002_triggers_solo_agregado.py` ya instala el trigger de sólo agregado sobre `historial_estado_orden` (además de `movimiento_stock` e `historial_precio_repuesto`).
- C-06 aporta `Cliente`, `Vehiculo`, `VehiculoRepository.get_by_id_con_cliente` y `OrdenTrabajoRepository.contar_ordenes_abiertas`; C-07 aporta `Repuesto`, `MovimientoStock`, `RepuestoRepository.get_para_actualizar` y `MovimientoStockRepository` de sólo agregado.
- El patrón de módulo está consolidado en `app/modules/repuestos/`: repositorios flush-only, UoW con la misma sesión, contratos `extra="forbid"`, servicios con `async with uow:` y router con `requiere_rol`.
- `app/modules/ordenes/repository.py` ya existe en el árbol (traído como dependencia mínima de C-06); C-08 lo completa y lo integra, no lo reescribe desde cero.

## Goals / Non-Goals

**Goals:**

- Componer un módulo de órdenes que reutilice C-06 y C-07 sin duplicar repositorios ni reglas de stock.
- Garantizar atomicidad real en la terminación: stock, movimientos, estado e historial en un único commit.
- Resolver el detalle con un número constante de consultas, independiente de la cantidad de ítems.
- Dejar el catálogo de estados y el historial de estados como superficies de sólo lectura para la API.

**Non-Goals:**

- Editar el catálogo `estado_orden` desde la API (sólo lo siembra `seed.py`).
- Reponer stock o modificar precios desde el módulo de órdenes.
- Notificaciones reales (el aviso es simulado, Ej. 8).
- Verificación con PostgreSQL real de triggers y concurrencia, que corresponde a C-09.

## Decisions

### D1. Composición del módulo y `OrdenesUnitOfWork`

`OrdenesUnitOfWork(UnitOfWork)` construye sobre **una sola `AsyncSession`**:

- `estados` → `EstadoOrdenRepository` (nuevo, sólo lectura).
- `ordenes` → `OrdenTrabajoRepository` (existente, con `get_detalle`, `get_para_actualizar`, listados y conteos).
- `items` → `ItemOrdenRepository` (existente, más `listar_por_orden` y `get_para_actualizar_por_orden`).
- `historial` → `HistorialEstadoOrdenRepository` (sólo agregado: `add` + `listar_por_orden`, bloquea `update`/`delete`).
- `vehiculos` → `VehiculoRepository` de C-06.
- `repuestos` → `RepuestoRepository` de C-07.
- `movimientos` → `MovimientoStockRepository` de C-07.

**Por qué**: reutiliza las invariantes de C-03/C-06/C-07 y hace que la terminación comparta sesión y transacción con el descuento de stock y los movimientos. **Alternativa descartada**: un servicio que instancie sesiones o repositorios por su cuenta, que rompería la atomicidad y el contrato de capas `Router → Service → UoW → Repository → Model`.

### D2. Modelos, migración autogenerada y migración manual

Los modelos **ya existen**; la tarea es auditarlos y fijarlos al esquema:

1. Verificar tipos y restricciones: `OrdenTrabajo.total` `Numeric(12,2)` con CHECK `>= 0`; `ItemOrden.precio_unitario` `Numeric(10,2)` con CHECK `> 0`; `cantidad > 0`; `UNIQUE(orden_id, repuesto_id)`; `creada_en`/`cuando` con zona horaria.
2. Generar la **migración autogenerada** `003_ordenes_schema_sync` con `alembic revision --autogenerate`. El resultado esperado es **sin drift**; si autogenerate no detecta operaciones, la revisión se documenta como no-op explícita y no se inventan cambios de esquema.
3. Agregar la **migración manual** `004_ordenes_triggers_y_fk`, idempotente, que:
   - garantiza la FK `movimiento_stock.orden_id → orden_trabajo.id` y su índice si una base ya desplegada no los tuviera (`DO $$ ... IF NOT EXISTS` sobre `pg_constraint`/`pg_indexes`);
   - reinstala con `CREATE OR REPLACE` la función `prohibir_update_delete()` y el trigger de sólo agregado sobre `historial_estado_orden` (cubre bases creadas antes de la migración 002 y es inocuo si ya existe).

**Por qué**: el esquema real y los triggers son preexistentes, pero la consigna exige dejar la migración autogenerada y la manual como artefactos auditables. La migración manual con guardas evita fallar en bases nuevas y en bases ya migradas. **Alternativa descartada**: duplicar tablas o triggers sin guardas, que rompería `alembic upgrade head` en instalaciones existentes.

### D3. Catálogo de estados de sólo lectura

`EstadoOrdenRepository` **no hereda** de `BaseRepository`: su PK es `codigo`, no `id`, y no debe ofrecer `add`, `update` ni `delete`. Expone `listar_por_posicion()`, `get_by_codigo(codigo)` y `contar()`. El router sólo publica `GET /estados-orden`; no hay rutas de escritura.

El alta de orden comprueba que `PENDIENTE` exista en el catálogo. Si el catálogo está vacío (o no contiene `PENDIENTE`), responde 409 con mensaje propio antes de escribir nada (RN-19). **Alternativa descartada**: hardcodear estados en Python sin consultar el catálogo, que contradice RN-19.

### D4. Alta de orden: precios copiados y total en servidor

`POST /ordenes` recibe `vehiculo_id`, `falla` e `items: [{repuesto_id, cantidad}]`. El contrato prohíbe `precio_unitario`, `subtotal`, `total`, `estado` y `mecanico_id` por `extra="forbid"` (422).

Dentro de un único `async with uow:`:

1. Valida catálogo con `PENDIENTE` (409 si falta).
2. Carga el vehículo vigente con su cliente (`get_by_id_con_cliente`; 409 si no existe o está borrado).
3. Rechaza ítems repetidos (422) y cantidades no positivas (422, también en el contrato).
4. Por cada ítem obtiene el repuesto vigente (`SoftDeleteRepository.get_by_id` filtra `borrado_en`); si falta, 409 sin crear nada.
5. Copia `precio_unitario = repuesto.precio` y calcula `subtotal`/`total` con `Decimal` (nunca `float`).
6. Inserta la orden con `estado="PENDIENTE"`, `mecanico_id=None`, `total` calculado; luego los ítems y la primera línea `HistorialEstadoOrden(desde_estado=None, hasta_estado="PENDIENTE", usuario_id=actor.id)`.

El precio y el total del cliente se ignoran porque el contrato no los acepta. **Alternativa descartada**: recalcular precios en la respuesta de lectura, que haría variar el histórico cuando cambie el precio del repuesto.

### D5. Terminación atómica con bloqueo determinista

`POST /ordenes/{id}/terminar`:

1. Autoriza: `actor.id == orden.mecanico_id` o rol `ADMIN` (403 en caso contrario).
2. Exige `estado == "EN_REPARACION"` (409).
3. **Bloquea la orden** (`SELECT ... FOR UPDATE` vía `get_para_actualizar`) para que dos terminaciones concurrentes no descuenten stock dos veces.
4. Bloquea los repuestos involucrados **ordenados por `repuesto_id` ascendente** (`get_para_actualizar`), evitando interbloqueos entre órdenes con ítems cruzados.
5. Valida **todos** los stocks antes de escribir: si alguno es insuficiente, lanza 409 y el UoW revierte sin tocar stock, movimientos, estado ni historial.
6. Aplica `repuesto.stock -= cantidad` y `movimientos.add(MovimientoStock(cantidad=-cantidad, motivo=f"SALIDA POR ORDEN {orden.id}", orden_id=orden.id, usuario_id=actor.id))` por ítem.
7. Cambia la orden a `TERMINADA`, inserta `HistorialEstadoOrden(desde_estado="EN_REPARACION", hasta_estado="TERMINADA", usuario_id=actor.id)` y confirma.

El mensaje de motivo no lleva datos sensibles. **Alternativa descartada**: `UPDATE repuesto SET stock = stock - :n` suelto, que impediría validar los cuatro efectos en la misma transacción y auditar el movimiento.

### D6. `BackgroundTasks` para el aviso simulado

El **router** recibe `BackgroundTasks` y, **después** de que el servicio retorna (es decir, con el commit ya confirmado por el UoW), agenda `avisar_cliente_simulado(orden_id, destinatario)`:

- `await asyncio.sleep(0.5)` y `logger.info("Aviso simulado: orden %s terminada...", ...)`.
- La tarea no abre sesión ni consulta la base: recibe sólo datos ya calculados.
- Se envuelve en `try/except` para que un fallo del aviso no afecte la respuesta ya emitida.

Si la terminación falla, el servicio lanza excepción y el router nunca agenda la tarea. **Alternativa descartada**: agendar la tarea dentro del servicio antes del commit, que podría notificar una orden que luego se revierte.

### D7. Carga anticipada sin N+1

`OrdenTrabajoRepository.get_detalle` usa `selectinload` en cadena: `vehiculo → cliente`, `items → repuesto`, `historial_estados` (y `mecanico` si se expone). `listar` y `listar_por_cliente_usuario` precargan `vehiculo`.

El historial se devuelve ordenado por `cuando, id`; el orden de la colección se fija en la respuesta para no depender del orden de carga. **Por qué**: `selectinload` emite una consulta por relación, constante respecto de la cantidad de ítems, en lugar de una por ítem como `lazy="select"` (riesgo real de N+1 en async). **Alternativa descartada**: `joinedload` con colecciones, que duplicaría filas y complicaría la paginación.

### D8. Cancelación: permisos antes que estado

`POST /ordenes/{id}/cancelar`:

1. Carga la orden con vehículo y cliente.
2. Determina permiso: `ADMIN`, `RECEPCION` o `CLIENTE` dueño (`vehiculo.cliente.usuario_id == actor.id`). Si no cumple → **403**, sin mirar el estado (RN-12).
3. Recién entonces exige `estado == "PENDIENTE"`; si no → **409**.
4. Pasa a `CANCELADA` e inserta la línea de historial en el mismo UoW.

`MECANICO` no cancela según la matriz RBAC, por lo que recibe 403. **Alternativa descartada**: validar el estado primero, que devolvería 409 a un actor sin permiso y filtraría información del estado de la orden.

### D9. Inicio de orden

`POST /ordenes/{id}/iniciar` exige rol `MECANICO` vigente (consulta en base vía `requiere_rol`). Con la orden bloqueada: si no está `PENDIENTE` → 409; en caso contrario asigna `mecanico_id = actor.id`, pasa a `EN_REPARACION` e inserta historial. El autoasignado no puede cambiarse por payload.

### D10. `GET /mis-ordenes` y autorización del detalle

- `mis-ordenes` usa `listar_por_cliente_usuario`/`contar_por_cliente_usuario`, que unen `OrdenTrabajo → Vehiculo → Cliente` y filtran `Cliente.usuario_id = actor.id` (RN-17). Un usuario de personal sin cliente vinculado obtiene lista vacía, no un error.
- El detalle permite personal (`ADMIN`/`RECEPCION`/`MECANICO`) y al `CLIENTE` dueño; cualquier otro cliente recibe 403 sin datos de la orden.

**Alternativa descartada**: filtrar en Python después de traer todas las órdenes, que expondría datos y rompería la paginación.

### D11. Contratos, RBAC y mapeo de errores

- `ItemOrdenRequest` sólo `repuesto_id` y `cantidad > 0`; `OrdenCrearRequest` con `falla` de 1 a 500 y `items` con `min_length=1`; respuestas con `Decimal` y `datetime` con zona horaria.
- Todos los schemas heredan `BaseSchema` (`extra="forbid"`).
- Router montado en el grupo Protegido con `requiere_password_actualizada`; cada endpoint declara `requiere_rol(...)` o `get_current_user` según la matriz.
- Se amplía `_CONSTRAINT_MAP` de `main.py`: `uq_item_orden_orden_repuesto` → 409/422, `ck_item_orden_cantidad_positiva`, `ck_item_orden_precio_positivo`, `ck_orden_trabajo_total_no_negativo` → 422, y las FK `orden_trabajo_vehiculo_id_fkey`, `item_orden_repuesto_id_fkey` → 404/400 con mensajes de negocio.
- Ningún mensaje incluye nombres de constraints, SQL ni trazas (RN-18).

### D12. Historial de estados: sólo agregado en API, repositorio y base

- API: no hay endpoints de escritura sobre el historial; se expone sólo dentro del detalle.
- Repositorio: `HistorialEstadoOrdenRepository` hereda de una base inmutable (como en C-07) y sólo permite `add` y consultas.
- Base: trigger de la migración 002, reinstalado idempotentemente por la 004.

### D13. Estrategia de pruebas

- SQLite en memoria (`test/infra_sqlite.py`) con la fachada `SesionFalsa` para router/servicio/repositorio/UoW.
- Cobertura explícita: precio/total calculados, 422 por campos extra, 422 por ítems vacíos/repetidos, 409 por vehículo/repuesto inválido, 409 por catálogo vacío, transiciones válidas e inválidas, 403 antes que 409 en cancelación, rollback total por stock insuficiente, `mis-ordenes` filtrado y detalle con consultas constantes (2 vs 4 ítems).
- El aviso simulado se prueba con `BackgroundTasks` real y `asyncio.sleep`/logger parcheados para no esperar 0.5 s por caso.
- Triggers PL/pgSQL y concurrencia real se difieren a C-09 (sin PostgreSQL disponible), igual que en C-07.

## Risks / Trade-offs

- **Doble descuento por terminaciones concurrentes** → bloqueo `FOR UPDATE` de la orden y de los repuestos, con orden de bloqueo determinista.
- **Interbloqueo entre órdenes con ítems cruzados** → los repuestos se bloquean siempre por `repuesto_id` ascendente.
- **El aviso simulado corre después del commit** → un fallo del aviso se captura y registra; nunca revierte la orden ni cambia la respuesta.
- **La migración 004 podría duplicar FK/trigger** → todas las operaciones usan guardas `IF NOT EXISTS`/`CREATE OR REPLACE` y su `downgrade` sólo elimina lo que la migración creó.
- **`003` autogenerada puede salir vacía** → se documenta como no-op explícita; no se fuerza drift artificial ni se agregan columnas que la KB no pide.
- **SQLite no reproduce los triggers ni el índice parcial** → las pruebas de inmutabilidad física y concurrencia quedan marcadas para C-09; la suite local valida la lógica de aplicación.
- **`get_detalle` con `selectinload`** → si en el futuro se pagina el historial o los ítems, habrá que revisar el número de consultas; el spec exige que sea independiente de la cantidad de ítems, no del tamaño de la página del historial.

## Migration Plan

1. `alembic heads` → confirmar `002_triggers_solo_agregado`.
2. `alembic revision --autogenerate -m "ordenes schema sync"` → revisar que no haya drift; renombrar a `003_ordenes_schema_sync`.
3. Escribir a mano `004_ordenes_triggers_y_fk` con guardas de FK/índice y `CREATE OR REPLACE` del trigger de `historial_estado_orden`.
4. `alembic upgrade head` y `alembic current` → `004_ordenes_triggers_y_fk`.
5. Verificar `seed.py` (estados `PENDIENTE`, `EN_REPARACION`, `TERMINADA`, `CANCELADA` con `es_final` correcto).
6. **Rollback**: `alembic downgrade 002_triggers_solo_agregado` revierte la 004 (sólo lo que ella creó) y la 003; el código se revierte retirando el módulo y el montaje del router.

## Open Questions

Ninguna que afecte specs, enfoque o tareas. El nombre del change (`ordenes-trabajo-module`) difiere del rótulo de `CHANGES.md` (`ordenes-trabajo-execution-module`) por pedido explícito del usuario; la funcionalidad es la misma.
