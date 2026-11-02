# Tasks: clientes-vehiculos-module

## 1. Contratos DTO (Schemas)

- [x] 1.1 Implementar `ClienteCreateRequest`, `ClienteResponse` y `ClienteDetalleResponse` en `app/modules/clientes/schemas.py` con `extra="forbid"`.
- [x] 1.2 Implementar `VehiculoCreateRequest` y `VehiculoResponse` en `app/modules/clientes/schemas.py` con normalización de patente (mayúsculas, sin espacios) y rango de año 1950..2100.

## 2. Servicios de Dominio (Services)

- [x] 2.1 Implementar `ClienteService` en `app/modules/clientes/service.py` con alta transaccional, detección de documento duplicado (409) y consulta por ID con precarga de vehículos vigentes.
- [x] 2.2 Implementar `VehiculoService` en `app/modules/clientes/service.py` con alta de vehículo validando patente activa única (409), baja lógica con rechazo 409 si existen órdenes abiertas (RN-16) y consulta de vehículos propios (RN-17).

## 3. Controladores y Montaje (Routers & Integration)

- [x] 3.1 Crear `app/modules/clientes/router.py` implementando los endpoints `POST /clientes`, `GET /clientes/{id}`, `POST /clientes/{id}/vehiculos`, `DELETE /vehiculos/{id}` y `GET /mis-vehiculos` con dependencias RBAC.
- [x] 3.2 Registrar el router de clientes en `main.py` dentro del grupo protegido con `requiere_password_actualizada`.

## 4. Pruebas y Validación (Tests & Verification)

- [x] 4.1 Crear `test/test_clientes_service.py` verificando casos de servicio sobre SQLite: altas, documento duplicado, patente duplicada, reutilización de patente borrada y bloqueo por órdenes abiertas (RN-16).
- [x] 4.2 Crear `test/test_clientes_router.py` verificando contratos, respuestas HTTP (201, 200, 204, 401, 403, 404, 409, 422) y control RBAC de `ADMIN`, `RECEPCION` y `CLIENTE`.
- [x] 4.3 Ejecutar las suites de pruebas y validar ausencia de regresiones.

## Workflow follow-up

- Sincronizar las especificaciones con `openspec/specs/`.
- Archivar el change completado y actualizar `CHANGES.md`.
