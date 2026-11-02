# Proposal

## Why

Todos los módulos funcionales del taller mecánico (C-01 a C-08) están implementados y probados mediante tests unitarios y de integración con SQLite. Sin embargo, para la entrega y evaluación formal de la cátedra se requiere la suite canónica de pruebas end-to-end (.http y SQL) que demuestre los 19 casos de prueba mínimos (C-01 a C-19) contra el servidor HTTP real, la verificación de cero consultas N+1 con `SQL_ECHO=true`, la validación de los disparadores PL/pgSQL de sólo agregado en PostgreSQL (`solo_agregado.sql`), la plantilla de entorno limpia (`env.example`) y el manual operativo paso a paso (`README.md`) para levantar el sistema desde cero.

## What Changes

- Creación de la suite de pruebas HTTP de cátedra en `test/` ejecutable con la extensión "REST Client" (o herramientas compatibles) con soporte de multi-sesión (`# @no-cookie-jar` y cookies dinámicas por rol):
  - `test/auth.http`: Casos C-01 a C-09 (parámetros inválidos, registro atómico sin filas huérfanas, cookie HttpOnly, login timing-safe, bloqueo por fuerza bruta en `intento_acceso`, RBAC 401 vs 403, revocación de rol en caliente, autoprotección admin y cambio obligatorio de contraseña).
  - `test/ordenes.http`: Casos C-10 a C-13 (alta con dos ítems y precios de servidor, fallo y rollback total por falta de stock, reposición y terminación exitosa con aviso en BackgroundTasks, y cancelación evaluando permisos antes de estado).
  - `test/repuestos_vehiculos.http`: Casos C-16 a C-19 (búsqueda anti SQL injection, paginación estricta, prohibición de edición de stock por PATCH, catálogo de estados ordenado, auditoría de precios en `historial_precio_repuesto`, y reciclado de patente tras baja de vehículo mediante índice único parcial).
- Completitud de `test/solo_agregado.sql`: verificación de los 6 rechazos de `UPDATE`/`DELETE` sobre las tablas de sólo agregado (`historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto`) más el caso 7 de rechazo de inserción de orden con estado fuera del catálogo por clave foránea (Caso C-14).
- Script/prueba automatizada y evidencia documentada de verificación de cero consultas N+1 (`SQL_ECHO=true`), comprobando número idéntico de consultas SQL para órdenes de 2 y 4 ítems (Caso C-15).
- Validación y completitud de `env.example` con todas las variables requeridas por `pydantic-settings` sin secretos reales y con instrucciones de generación de claves.
- Creación de `README.md` canónico con guía de instalación paso a paso: requisitos, entorno virtual, dependencias, variables de entorno, migraciones con Alembic (`upgrade head`), datos semilla (`seed.py`), ejecución del servidor ASGI con Uvicorn y corrida de la suite de pruebas.

## Capabilities

### New Capabilities

- `e2e-verification`: Especificación de la suite de pruebas end-to-end de cátedra (C-01 a C-19), harness de pruebas `.http` con soporte multi-sesión, validación estricta de invariantes de base de datos (disparadores de sólo agregado y FKs en PostgreSQL), verificación de consultas N+1 y manual de puesta en marcha reproducible.

### Modified Capabilities

- Ninguna. Las capacidades funcionales previas se mantienen inalteradas; este change agrega la verificación e2e y la documentación operativa final.

## Impact

- **Código y artefactos**:
  - `test/auth.http`, `test/ordenes.http`, `test/repuestos_vehiculos.http` (nuevos).
  - `test/solo_agregado.sql` (actualizado con el caso de clave foránea).
  - `env.example` (auditado y documentado).
  - `README.md` (nuevo).
  - `test/test_c15_n_plus_one.py` (o harness equivalente para certificar C-15).
- **APIs**: Ningún cambio a contratos existentes. Se consumen los endpoints existentes de auth, clientes, repuestos y órdenes.
- **Base de datos**: Sin modificaciones de esquema.
