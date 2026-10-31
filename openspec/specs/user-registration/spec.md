# user-registration Specification

## Purpose
Permite que cualquier persona se registre como cliente del taller en una operación atómica que garantiza que el usuario, su rol CLIENTE y su ficha de cliente quedan creados todos juntos o ninguno.

## Requirements

### Requirement: Auto-registro atómico de cliente
`POST /auth/registro` SHALL crear dentro de un único UoW: el registro de `usuario`, la asignación del rol `CLIENTE` en `asignacion_rol` y la ficha en `cliente`. Si cualquier paso falla, el rollback revierte las tres filas.

#### Scenario: Registro exitoso
- **WHEN** se envía `POST /auth/registro` con email, contraseña y documento únicos
- **THEN** la respuesta es HTTP 201 con los datos del usuario creado, y existen las filas en `usuario`, `asignacion_rol` (rol=CLIENTE) y `cliente`

#### Scenario: Email duplicado
- **WHEN** se envía `POST /auth/registro` con un email que ya existe
- **THEN** la respuesta es HTTP 409 sin exponer trazas internas de la base de datos y no quedan filas parciales

#### Scenario: Documento ya asociado a cliente
- **WHEN** se envía `POST /auth/registro` con un número de documento que ya pertenece a un cliente existente del taller
- **THEN** la respuesta es HTTP 409 y el sistema no asocia la cuenta nueva a la ficha existente

### Requirement: Contraseña hasheada antes de persistir
El sistema SHALL almacenar exclusivamente el hash bcrypt de la contraseña. El valor en texto plano MUST NOT persistirse ni aparecer en ninguna respuesta.

#### Scenario: Hash almacenado
- **WHEN** se completa el registro exitosamente
- **THEN** la columna `password_hash` del usuario contiene un hash bcrypt válido, no el texto plano

#### Scenario: Respuesta sin credencial
- **WHEN** `POST /auth/registro` responde HTTP 201
- **THEN** el cuerpo de la respuesta no incluye `password_hash` ni la contraseña en texto plano
