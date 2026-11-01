# api-error-handling Specification

## Purpose

Traduce los errores de integridad de la base de datos a respuestas HTTP de negocio predecibles, sin exponer SQL, nombres de restricciones ni trazas internas de PostgreSQL.

## Requirements

### Requirement: Traducción de violaciones de unicidad
Una violación de una restricción UNIQUE conocida SHALL responder HTTP 409 con un mensaje de negocio. La transacción SHALL revertirse y no SHALL quedar ninguna fila parcial de la operación rechazada.

#### Scenario: Email duplicado
- **WHEN** una inserción viola la unicidad de `usuario.email`
- **THEN** responde HTTP 409 con un mensaje de negocio y no queda ninguna fila nueva

#### Scenario: Asignación abierta duplicada
- **WHEN** una inserción viola el índice único parcial de `asignacion_rol`
- **THEN** responde HTTP 409 y la transacción revierte completa

### Requirement: Traducción de violaciones de referencia
Una violación de clave foránea conocida SHALL responder HTTP 404 cuando la referencia es a un usuario inexistente, con un mensaje de negocio. Una violación de una restricción CHECK conocida SHALL responder HTTP 422.

#### Scenario: Referencia a un recurso inexistente
- **WHEN** una inserción referencia una fila que no existe
- **THEN** responde HTTP 404 con un mensaje de negocio

#### Scenario: Valor rechazado por CHECK
- **WHEN** una inserción viola una restricción CHECK conocida
- **THEN** responde HTTP 422 con un mensaje de negocio

### Requirement: Sólo restricciones conocidas se traducen
El handler SHALL traducir únicamente las restricciones incluidas en una lista explícita de códigos y nombres conocidos. Cualquier otro error de integridad SHALL responder HTTP 400 con un mensaje genérico, sin convertirlo en 500 y sin revelar información del esquema.

#### Scenario: Restricción desconocida
- **WHEN** se produce un error de integridad que no está en la lista conocida
- **THEN** responde HTTP 400 con un mensaje genérico

#### Scenario: Error ajeno a la integridad
- **WHEN** se produce una excepción que no es `IntegrityError`
- **THEN** el handler de integridad no la intercepta

### Requirement: Respuestas sin detalles internos
La respuesta al cliente NO SHALL incluir el texto original de PostgreSQL, nombres de tablas o columnas, nombres de constraints, sentencias SQL ni trazas. El detalle técnico SHALL quedar únicamente en el registro del servidor.

#### Scenario: Cuerpo de error limpio
- **WHEN** se traduce cualquier error de integridad
- **THEN** el cuerpo sólo contiene un mensaje de negocio y ningún fragmento de SQL ni nombre de restricción

#### Scenario: Violación de unicidad no filtra la columna
- **WHEN** falla la unicidad de una columna
- **THEN** la respuesta no menciona el nombre de la columna ni el valor enviado
