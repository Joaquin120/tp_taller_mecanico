# Tasks

## 1. Modelos Declarativos de Dominio

- [x] 1.1 Implementar `app/modules/usuarios/models.py` con `Usuario`, `AsignacionRol`, `IntentoAcceso`, `EventoSeguridad`, validación de CHECK de roles, índice único parcial con `postgresql_where` y relación 1-a-1 `Usuario.cliente` con `uselist=False`
- [x] 1.2 Implementar `app/modules/clientes/models.py` con `Cliente` y `Vehiculo`, agregando CHECK `anio BETWEEN 1950 AND 2100` e índice único parcial sobre `patente` para soft-delete
- [x] 1.3 Implementar `app/modules/repuestos/models.py` con `Repuesto`, `MovimientoStock`, `HistorialPrecioRepuesto`, restricciones CHECK (`precio > 0`, `stock >= 0`, `precio_nuevo <> precio_anterior`) e índice único parcial sobre `codigo`
- [x] 1.4 Implementar `app/modules/ordenes/models.py` con `EstadoOrden` (catálogo con PK textual `codigo`), `OrdenTrabajo`, `ItemOrden`, `HistorialEstadoOrden`, claves foráneas a `estado_orden`, CHECKs de totales y unicidad `(orden_id, repuesto_id)`

## 2. Infraestructura y Migraciones Alembic

- [x] 2.1 Configurar `alembic.ini` y `migrations/env.py` con soporte asincrónico integrando `Settings.database_url` y la importación de todos los modelos de `SQLModel.metadata`
- [x] 2.2 Generar y revisar la migración 001 (`001_initial_schema`) conteniendo las 13 tablas, restricciones CHECK, claves foráneas e índices únicos parciales
- [x] 2.3 Crear la migración 002 manual (`002_triggers_solo_agregado`) con la función PL/pgSQL `prohibir_update_delete()` y los 3 disparadores `BEFORE UPDATE OR DELETE` sobre las tablas append-only

## 3. Siembra Determinística y Verificación

- [x] 3.1 Implementar el script asincrónico `seed.py` con vaciado mediante `TRUNCATE ... CASCADE` y carga del catálogo de estados, usuarios de prueba con hash bcrypt, clientes Laura y Jorge con sus vehículos, repuestos con movimientos iniciales, órdenes e historiales
- [x] 3.2 Implementar pruebas de persistencia en `test/test_persistence.py` verificando el comportamiento de los modelos, restricciones CHECK, unicidad parcial, disparadores de sólo agregado y ejecución de `seed.py`

## Workflow follow-up

- Verificar `openspec validate domain-models-migrations-seed`.
- Proceder al apply workflow tras aprobación del usuario.
