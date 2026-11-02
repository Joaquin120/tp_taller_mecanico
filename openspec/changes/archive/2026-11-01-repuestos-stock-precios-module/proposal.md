# Proposal

## Why

El taller necesita administrar su catálogo de repuestos para poder cotizar y ejecutar órdenes de trabajo. Hoy sólo existe la capa de persistencia (`repuesto`, `movimiento_stock`, `historial_precio_repuesto` creadas en C-02), sin API que permita consultar, dar de alta, reponer stock o actualizar precios. Sin este módulo, `C-08 ordenes-trabajo-execution-module` no puede copiar precios vigentes ni descontar stock.

## What Changes

- Nuevo módulo `app/modules/repuestos/` con repositorio, Unit of Work, contratos Pydantic, servicio y router.
- `GET /repuestos`: listado paginado con búsqueda por descripción (`q`) sobre repuestos vigentes.
- `GET /repuestos/{id}`: detalle de un repuesto vigente.
- `POST /repuestos`: alta con `stock_inicial`; genera el `movimiento_stock` inicial en el mismo UoW.
- `PATCH /repuestos/{id}`: modifica descripción y/o precio. El campo `stock` se rechaza con 422 (`extra="forbid"`). Si el precio cambia, inserta `historial_precio_repuesto` en la misma transacción; si es idéntico, no inserta fila.
- `DELETE /repuestos/{id}`: borrado lógico (`borrado_en`), responde 204.
- `POST /repuestos/{id}/reponer`: incrementa stock y registra `movimiento_stock` en el mismo UoW.
- `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios`: historial paginado de sólo lectura.
- Montaje del router en el grupo Protegido de `main.py` con las dependencias RBAC existentes.

No hay cambios de esquema: el índice único parcial `uq_repuesto_codigo_activo`, los CHECK de precio/stock y los triggers PL/pgSQL de sólo agregado ya fueron creados por las migraciones `001_initial_schema` y `002_triggers_solo_agregado` de C-02.

## Capabilities

### New Capabilities

- `spare-parts-inventory`: catálogo de repuestos con búsqueda y paginación, alta con stock inicial, reposición de stock, actualización de descripción/precio con historial atómico, borrado lógico y consulta de movimientos e historial de precios.

### Modified Capabilities

- Ninguna. `domain-persistence` y `data-access-contracts` ya cubren el esquema, los triggers y las abstracciones de acceso a datos; C-07 sólo consume esos contratos.

## Impact

- **Código**: `app/modules/repuestos/{repository,unit_of_work,schemas,service,router}.py`; `main.py` (incluir router); `test/` (pruebas del módulo).
- **API**: 8 endpoints nuevos bajo el grupo Protegido; lectura para ADMIN/RECEPCION/MECANICO y mutaciones sólo ADMIN.
- **Base de datos**: sin migraciones nuevas. Se reutilizan las tablas y los triggers existentes.
- **Dependencias**: sin dependencias nuevas; se usan `BaseRepository`, `SoftDeleteRepository`, `UnitOfWork`, `ParamsPaginacion`/`armar_paginacion` y `requiere_rol`.
- **Changes posteriores**: desbloquea `C-08 ordenes-trabajo-execution-module` (precios vigentes y descuento de stock).
