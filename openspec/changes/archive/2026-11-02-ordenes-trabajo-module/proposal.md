# Proposal

## Why

Las tablas `estado_orden`, `orden_trabajo`, `item_orden` e `historial_estado_orden` existen desde C-02, y C-06/C-07 ya exponen vehículos y repuestos con stock y precio vigente, pero no hay API que permita abrir, iniciar, terminar, cancelar o consultar órdenes de trabajo. Sin ese ciclo de vida el taller no puede ejecutar su proceso central y `C-09 verification-suite-e2e-docs` no tiene flujo que verificar de punta a punta.

## What Changes

- Nuevo módulo `app/modules/ordenes/` con modelos verificados, repositorios, Unit of Work, contratos Pydantic, servicio y router.
- `GET /estados-orden`: catálogo `estado_orden` de **sólo lectura**, ordenado por `posicion`. La API no expone alta, edición ni baja de estados (RN-19).
- `POST /ordenes`: la orden **nace siempre `PENDIENTE`**. El payload sólo acepta `vehiculo_id`, `falla` e `items: [{repuesto_id, cantidad}]`; **el precio y el total nunca viajan desde el cliente**. El servidor copia el `precio` vigente de cada repuesto, calcula `subtotal = precio × cantidad` y el `total` como suma de subtotales. Rechaza 422 con lista vacía o repuestos repetidos, 409 si el catálogo de estados está vacío o el vehículo/repuesto no está vigente, e inserta la primera fila de `historial_estado_orden` (`desde_estado = NULL`, `hasta_estado = PENDIENTE`) en la misma transacción.
- `GET /ordenes` (paginado y filtrable por `estado`) y `GET /ordenes/{id}`: el detalle exige **carga anticipada** de vehículo, cliente, ítems, repuestos e historial en una sola consulta por relación (`selectinload`), sin N+1. Un `CLIENTE` sólo puede ver órdenes de sus propios vehículos (403 en caso contrario).
- `POST /ordenes/{id}/iniciar`: sólo `MECANICO`; autoasigna `mecanico_id` al actor y pasa `PENDIENTE → EN_REPARACION` (RN-11).
- `POST /ordenes/{id}/terminar`: el mecánico asignado o un `ADMIN` finaliza la orden en **un único Unit of Work atómico**: valida stock suficiente de todos los ítems, descuenta `repuesto.stock`, inserta un `movimiento_stock` por ítem (`cantidad` negativa, `orden_id` de la orden), pasa a `TERMINADA` e inserta la línea de historial. Si falta stock de cualquier repuesto, **falla toda la operación y no queda ninguna escritura** (RN-13, HTTP 409). Tras el commit exitoso se agenda un `BackgroundTask` que simula el aviso al cliente (`asyncio.sleep(0.5)` + log).
- `POST /ordenes/{id}/cancelar`: evalúa primero la **propiedad del vehículo / permisos** y después el estado; por eso un actor sin permiso recibe **403 antes que 409**. Sólo cancela una orden `PENDIENTE` (RN-12, RN-11).
- `GET /mis-ordenes`: órdenes de los vehículos del cliente autenticado, paginadas y filtradas por `cliente_id` (RN-17).
- Esquema: los modelos y las tablas ya existen desde C-02. El change **verifica** su mapeo, genera la migración autogenerada para detectar drift y agrega una **migración manual idempotente** que garantiza el trigger PL/pgSQL de sólo agregado sobre `historial_estado_orden` y la clave foránea `movimiento_stock.orden_id → orden_trabajo.id` (con su índice) en bases ya desplegadas.
- Montaje del router de órdenes en el grupo Protegido de `main.py`, junto a clientes y repuestos.

## Capabilities

### New Capabilities

- `work-order-lifecycle`: catálogo de estados de sólo lectura, alta de órdenes `PENDIENTE` con precio copiado y total calculado en servidor, consulta paginada y detalle con carga anticipada, transiciones `iniciar`/`terminar`/`cancelar` con RBAC y propiedad, terminación atómica con descuento de stock y movimientos, y consulta de órdenes propias del cliente.

### Modified Capabilities

- Ninguna. `spare-parts-inventory` ya declara que el stock sólo cambia por alta con stock inicial, reposición o terminación de orden, y `data-access-contracts` ya cubre UoW, repositorios, paginación y contratos estrictos: C-08 consume esos contratos sin modificarlos.

## Impact

- **Código**: `app/modules/ordenes/{models,repository,unit_of_work,schemas,service,router}.py`; `main.py` (import + montaje del router y ampliación de `_CONSTRAINT_MAP`); `test/test_ordenes_*.py` y extensión de `test/infra_sqlite.py` si el esquema lo requiere.
- **API**: 8 endpoints nuevos (`GET /estados-orden`, `POST/GET /ordenes`, `GET /ordenes/{id}`, `POST /ordenes/{id}/iniciar`, `POST /ordenes/{id}/terminar`, `POST /ordenes/{id}/cancelar`, `GET /mis-ordenes`) bajo el grupo Protegido.
- **Base de datos**: migración autogenerada de verificación y migración manual idempotente de trigger/FK. No se agregan tablas ni columnas nuevas.
- **Dependencias**: C-06 (`Cliente`, `Vehiculo` y `contar_ordenes_abiertas`) y C-07 (`Repuesto`, `MovimientoStock` y descuento de stock). Se reutilizan `BaseRepository`, `UnitOfWork`, `ParamsPaginacion`/`armar_paginacion`, `requiere_rol` y `get_current_user`. `BackgroundTasks` es parte de FastAPI/Starlette, sin dependencia nueva.
- **Nota de nomenclatura**: `CHANGES.md` rotula esta entrada como `C-08 ordenes-trabajo-execution-module`; el change se crea con el nombre solicitado `ordenes-trabajo-module` y la misma funcionalidad.
- **Changes posteriores**: desbloquea `C-09 verification-suite-e2e-docs` (suite `.http`, pruebas de triggers, validación de N+1, README de entrega).
