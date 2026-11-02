# Spec Delta: clientes-vehiculos

## Purpose
Proporciona la gestión integral de clientes y sus flotas vehiculares asociadas, garantizando unicidad de documento y patente activa, borrado lógico protegido contra órdenes en proceso y acceso seguro a vehículos propios.

## ADDED Requirements

### Requirement: Registro de clientes con documento único
El sistema SHALL permitir a usuarios con roles `ADMIN` o `RECEPCION` dar de alta clientes con nombre, documento y teléfono. El documento debe ser único en la base de datos (RN-01); ante un duplicado el sistema SHALL responder HTTP 409.

#### Scenario: Alta exitosa de cliente
- **WHEN** un usuario con rol `ADMIN` o `RECEPCION` envía una solicitud `POST /clientes` con datos válidos
- **THEN** el sistema registra el cliente en la base de datos y responde HTTP 201 con la información del cliente

#### Scenario: Documento duplicado
- **WHEN** se intenta registrar un cliente con un documento que ya pertenece a otro cliente registrado
- **THEN** el sistema rechaza la creación y responde HTTP 409 con detalle del conflicto

#### Scenario: Acceso no autorizado o sin credenciales
- **WHEN** un usuario no autenticado o con rol distinto de `ADMIN` o `RECEPCION` solicita `POST /clientes`
- **THEN** el sistema responde HTTP 401 si no hay sesión válida o HTTP 403 si el rol no tiene los permisos suficientes

### Requirement: Consulta de cliente con precarga de vehículos
El sistema SHALL permitir a usuarios con rol `ADMIN` o `RECEPCION` consultar los datos de un cliente por ID (`GET /clientes/{id}`), precargando exclusivamente sus vehículos vigentes (no borrados).

#### Scenario: Consulta de cliente existente
- **WHEN** un usuario con rol `ADMIN` o `RECEPCION` solicita `GET /clientes/{id}` de un cliente existente
- **THEN** el sistema responde HTTP 200 con los datos del cliente y la lista de sus vehículos vigentes asociados

#### Scenario: Consulta de cliente inexistente
- **WHEN** se solicita `GET /clientes/{id}` con un ID que no corresponde a ningún cliente
- **THEN** el sistema responde HTTP 404

### Requirement: Registro de vehículo con patente única activa
El sistema SHALL permitir a usuarios con rol `ADMIN` o `RECEPCION` registrar vehículos vinculados a un cliente (`POST /clientes/{id}/vehiculos`), validando patente única entre vehículos vigentes (RN-01) y año de fabricación entre 1950 y 2100. Se permite la reutilización de una patente que haya sido dada de baja previamente.

#### Scenario: Registro exitoso de vehículo
- **WHEN** se envía una solicitud válida `POST /clientes/{id}/vehiculos` para un cliente existente
- **THEN** el sistema registra el vehículo asociado y responde HTTP 201 con los datos del vehículo

#### Scenario: Patente duplicada en vehículo vigente
- **WHEN** se intenta registrar un vehículo cuya patente ya está asignada a un vehículo activo (sin fecha de baja)
- **THEN** el sistema rechaza la creación y responde HTTP 409

#### Scenario: Reutilización de patente de vehículo dado de baja
- **WHEN** se intenta registrar un vehículo con una patente que perteneció a un vehículo con borrado lógico (`borrado_en` no nulo)
- **THEN** el sistema permite el registro exitosamente y responde HTTP 201

#### Scenario: Año de fabricación inválido
- **WHEN** se envía un vehículo con año menor a 1950 o mayor a 2100
- **THEN** el sistema responde HTTP 422 con error de validación de contrato

### Requirement: Baja lógica de vehículos condicionada a órdenes abiertas
El sistema SHALL permitir a usuarios con rol `ADMIN` o `RECEPCION` solicitar la baja lógica de un vehículo (`DELETE /vehiculos/{id}`). Si el vehículo tiene órdenes de trabajo no finalizadas (`es_final=False`), el sistema SHALL rechazar la baja con HTTP 409 (RN-16). Si no tiene órdenes abiertas, SHALL establecer `borrado_en` con la fecha y hora actual y responder HTTP 204.

#### Scenario: Baja lógica rechazada por orden abierta
- **WHEN** se solicita la baja de un vehículo que tiene al menos una orden de trabajo en estado no final
- **THEN** el sistema rechaza la operación, preserva el vehículo activo y responde HTTP 409

#### Scenario: Baja lógica exitosa sin órdenes abiertas
- **WHEN** se solicita la baja de un vehículo que no tiene órdenes o cuyas órdenes asociadas están todas finalizadas
- **THEN** el sistema actualiza la fecha de borrado del vehículo y responde HTTP 204

#### Scenario: Vehículo inexistente o ya borrado
- **WHEN** se solicita la baja de un vehículo inexistente o que ya se encuentra dado de baja
- **THEN** el sistema responde HTTP 404

### Requirement: Consulta de vehículos propios por el cliente autenticado
El sistema SHALL permitir a los usuarios autenticados con rol `CLIENTE` consultar sus propios vehículos vigentes mediante `GET /mis-vehiculos` (RN-17), excluyendo vehículos dados de baja y vehículos de cualquier otro cliente.

#### Scenario: Consulta exitosa de vehículos propios
- **WHEN** un usuario con rol `CLIENTE` solicita `GET /mis-vehiculos` con su sesión activa
- **THEN** el sistema responde HTTP 200 con la lista de sus vehículos vigentes asociados a su ficha de cliente

#### Scenario: Cliente no puede ver vehículos ajenos ni borrados
- **WHEN** un cliente consulta sus vehículos
- **THEN** la respuesta contiene únicamente vehículos activos pertenecientes a su ID de cliente, omitiendo vehículos ajenos o con `borrado_en`
