# data-access-contracts Specification

## Purpose
Provee abstracciones transversales para acceso a datos transaccional desacoplado mediante Unit of Work, repositorios genéricos con soporte de borrado lógico y envoltorio estandarizado de respuestas paginadas.

## Requirements

### Requirement: Transactional Unit of Work Lifecycle
The system SHALL coordinate asynchronous database operations through a Unit of Work context manager that commits on clean exit and rolls back on unhandled exceptions without closing the session.

#### Scenario: Clean execution commits transaction automatically
- **WHEN** un bloque de Unit of Work finaliza sin excepciones
- **THEN** la transacción confirma los cambios en la base de datos automáticamente

#### Scenario: Exception inside block triggers automatic rollback
- **WHEN** ocurre una excepción no controlada dentro del contexto del Unit of Work
- **THEN** se ejecutan las operaciones de reversión (rollback) en la base de datos y la sesión permanece disponible sin ser cerrada

### Requirement: Repository Flush-Only Mutation
The system SHALL restrict generic repository mutation methods to session flush operations and prohibit calling session commit directly.

#### Scenario: Adding or updating entity flushes changes without committing
- **WHEN** se invoca una operación de inserción, actualización o borrado en el repositorio base
- **THEN** los cambios son volcados con `session.flush()` y la transacción permanece abierta para el Unit of Work

### Requirement: Soft Delete Entity Filtering
The system SHALL exclude soft-deleted entities from standard queries and provide an explicit soft deletion method.

#### Scenario: Querying entities excludes records with deletion timestamp
- **WHEN** se listan u obtienen entidades mediante el repositorio de borrado lógico
- **THEN** los registros con `borrado_en` no nulo son omitidos del resultado y del conteo total

#### Scenario: Soft deleting an entity marks deletion timestamp
- **WHEN** se ejecuta el borrado lógico sobre una entidad
- **THEN** se asigna el timestamp actual en el campo `borrado_en` y la fila no se elimina físicamente de la base de datos

### Requirement: Standardized Pagination Wrapper
The system SHALL package collection responses in a paginated envelope with structural validation and page boundary checks.

#### Scenario: Valid page and size parameters return paginated payload
- **WHEN** se solicita un listado con página y tamaño válidos dentro del rango de 1 a 100
- **THEN** la respuesta devuelve `{items, total, page, size, pages}` con los cálculos coherentes

#### Scenario: Requested page exceeding total pages rejected with 422
- **WHEN** se solicita una página mayor a la cantidad total de páginas calculables y existen elementos en el conjunto
- **THEN** el sistema rechaza la solicitud con un código HTTP 422 indicando fuera de rango

### Requirement: Strict Pydantic Contracts
The system SHALL reject unexpected input fields in base request contracts using forbidden extra attributes.

#### Scenario: Extra attributes in payload rejected with validation error
- **WHEN** se envía un campo no definido en el esquema contractual de entrada
- **THEN** la validación de Pydantic rechaza la solicitud indicando campo adicional no permitido
