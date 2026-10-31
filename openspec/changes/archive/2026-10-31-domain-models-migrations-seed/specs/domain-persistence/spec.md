# Spec Delta

## Purpose
Define el esquema relacional, modelos declarativos de dominio, restricciones de integridad con catálogo de estados, disparadores de sólo agregado y siembra determinística.

## ADDED Requirements

### Requirement: Relational Domain Integrity
The system SHALL persist domain entities enforcing database check constraints and partial unique indexes for active soft-deleted records.

#### Scenario: Re-registering previously deleted vehicle plate succeeds
- **WHEN** un vehículo existente con patente "AB123CD" posee fecha de baja lógica `borrado_en`
- **THEN** el sistema permite registrar un nuevo vehículo con la misma patente "AB123CD" manteniendo la unicidad parcial

#### Scenario: Negative stock or non-positive price rejected by database
- **WHEN** se intenta persistir o actualizar un repuesto con precio menor o igual a cero o stock negativo
- **THEN** la base de datos rechaza la operación mediante violación de restricción CHECK

#### Scenario: Active role assignment is unique per user
- **WHEN** un usuario posee un rol activo donde `revocada_en` es nulo
- **THEN** la base de datos rechaza asignar el mismo rol al usuario mientras la asignación previa no haya sido revocada

### Requirement: Order Status Catalog Referencing
The system SHALL require all order states and state transition histories to reference the `estado_orden` catalog table through foreign keys.

#### Scenario: Creating order with unregistered state rejected by foreign key
- **WHEN** se intenta crear una orden de trabajo con un código de estado inexistente en el catálogo
- **THEN** la base de datos rechaza la operación con una violación de clave foránea

#### Scenario: State catalog preloaded with terminal and non-terminal states
- **WHEN** el catálogo de estados es consultado tras la siembra inicial
- **THEN** contiene los estados `PENDIENTE`, `EN_REPARACION`, `TERMINADA` (final) y `CANCELADA` (final)

### Requirement: Append-Only Audit Protection
The database SHALL prohibit UPDATE and DELETE operations on historical and movement tables using PL/pgSQL triggers.

#### Scenario: Updating an order state history record is rejected
- **WHEN** un cliente o proceso intenta ejecutar un UPDATE sobre la tabla `historial_estado_orden`
- **THEN** el disparador de base de datos interrumpe la transacción levantando una excepción de operación no permitida

#### Scenario: Deleting a stock movement record is rejected
- **WHEN** un cliente o proceso intenta ejecutar un DELETE sobre la tabla `movimiento_stock`
- **THEN** el disparador de base de datos interrumpe la transacción levantando una excepción de operación no permitida

#### Scenario: Updating a spare part price history record is rejected
- **WHEN** un cliente o proceso intenta ejecutar un UPDATE o DELETE sobre la tabla `historial_precio_repuesto`
- **THEN** el disparador de base de datos interrumpe la transacción levantando una excepción de operación no permitida

### Requirement: Deterministic Seed Initialization
The system SHALL provide an automated seed procedure that resets tables and populates baseline catalogs, users, vehicles, stock and test orders.

#### Scenario: Executing seed resets database to canonical baseline
- **WHEN** se ejecuta el script `seed.py`
- **THEN** todas las tablas operativas son vaciadas en orden referencial y pobladas con los datos canónicos de prueba

#### Scenario: Seeded users have valid bcrypt password hashes and assigned roles
- **WHEN** los usuarios iniciales son sembrados
- **THEN** sus contraseñas están hasheadas con bcrypt y sus roles vigentes están registrados en `asignacion_rol`
