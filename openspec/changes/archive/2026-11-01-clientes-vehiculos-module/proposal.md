# Proposal: clientes-vehiculos-module

## Why
El sistema del taller mecánico requiere gestionar de forma segura y transaccional los clientes y sus vehículos asociados. Se necesita permitir el registro y consulta de fichas de clientes y flotas vehiculares por parte del personal de recepción y administración, protegiendo la integridad referencial y las reglas de negocio (RN-01 unicidad de documento y patente activa, RN-16 bloqueo de baja de vehículos con órdenes de trabajo en curso, y RN-17 acceso de clientes exclusivamente a sus vehículos vigentes).

## What Changes
- **Schemas**: Contratos de datos estrictos en Pydantic (`extra="forbid"`) para la creación y respuesta de clientes (`ClienteCreateRequest`, `ClienteResponse`, `ClienteDetalleResponse`) y vehículos (`VehiculoCreateRequest`, `VehiculoResponse`), con validación y normalización de patentes y restricción de año (1950 a 2100).
- **Servicios**:
  - `ClienteService`: Alta de cliente validando documento único (409 en conflicto) y consulta por ID con precarga de vehículos vigentes.
  - `VehiculoService`: Alta de vehículo validando patente única activa (409 en conflicto), baja lógica (`borrado_en`) condicionada a que no existan órdenes de trabajo abiertas/no finales (409 en conflicto según RN-16, 204 en éxito), y consulta de flota perteneciente al cliente autenticado (RN-17).
- **Routers**: Endpoints RESTful bajo el grupo protegido:
  - `POST /clientes` (Roles: `ADMIN`, `RECEPCION` -> 201)
  - `GET /clientes/{id}` (Roles: `ADMIN`, `RECEPCION` -> 200 con vehículos)
  - `POST /clientes/{id}/vehiculos` (Roles: `ADMIN`, `RECEPCION` -> 201)
  - `DELETE /vehiculos/{id}` (Roles: `ADMIN`, `RECEPCION` -> 204 o 409)
  - `GET /mis-vehiculos` (Rol: `CLIENTE` -> 200)
- **Integración**: Montaje del router de clientes/vehículos en `main.py` protegido por `requiere_password_actualizada`.
- **Pruebas**: Suite de pruebas exhaustiva unitaria y de integración para validar códigos de respuesta HTTP, RBAC y consistencia transaccional con UoW.

## Capabilities

### New Capabilities
- `clientes-vehiculos`: Gestión del ciclo de vida de clientes y flotas vehiculares, reglas de unicidad, borrado lógico con validación de órdenes activas (RN-16) y consulta de vehículos propios (RN-17).

### Modified Capabilities
<!-- Ninguna especificación existente cambia sus requerimientos de nivel de spec -->

## Impact
- **Modelos y Repositorios**: Reutiliza `Cliente`, `Vehiculo`, `ClienteRepository`, `VehiculoRepository` y `ClientesUnitOfWork` ya implementados.
- **Rutas**: Se agregan `/clientes`, `/clientes/{id}`, `/clientes/{id}/vehiculos`, `/vehiculos/{id}`, y `/mis-vehiculos`.
- **Seguridad**: Integración con dependencias RBAC `requiere_rol` (`ADMIN`, `RECEPCION`, `CLIENTE`) y `get_usuario_actual`.
