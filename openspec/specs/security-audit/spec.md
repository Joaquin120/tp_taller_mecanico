# security-audit Specification

## Purpose

Registra en una tabla de sólo agregado las acciones sensibles de seguridad y permite a los administradores consultarlas de forma paginada.

## Requirements

### Requirement: Registro de eventos de seguridad
Las altas de personal, las asignaciones y revocaciones de rol y los cambios de contraseña SHALL registrar una fila en `evento_seguridad` con `cuando`, `actor` y `accion`, dentro del mismo UoW de la operación. El `actor` SHALL ser el email del usuario autenticado que ejecuta la acción, o `SISTEMA` cuando la acción no proviene de una sesión.

#### Scenario: Alta de personal auditada
- **WHEN** un ADMIN crea un usuario mediante `POST /usuarios`
- **THEN** se inserta un evento con `actor` igual al email del ADMIN y una acción de alta

#### Scenario: Asignación de rol auditada
- **WHEN** un ADMIN asigna un rol
- **THEN** se inserta un evento con el actor y una acción de asignación

#### Scenario: Revocación de rol auditada
- **WHEN** un ADMIN revoca un rol
- **THEN** se inserta un evento con el actor y una acción de revocación

#### Scenario: Cambio de contraseña auditado
- **WHEN** un usuario autenticado cambia su contraseña
- **THEN** se inserta un evento con su email y una acción de cambio de contraseña

#### Scenario: Rollback no deja evento
- **WHEN** la operación de seguridad falla y el UoW revierte
- **THEN** no queda ningún evento de esa operación

### Requirement: Consulta paginada de eventos
`GET /eventos` SHALL devolver los eventos ordenados por `cuando` descendente con el envoltorio `{items, total, page, size, pages}`, accesible sólo para ADMIN. `page` SHALL empezar en 1, `size` SHALL ir de 1 a 100 y una página fuera de rango SHALL responder 422.

#### Scenario: Consulta de un administrador
- **WHEN** un ADMIN llama a `GET /eventos` con `page` y `size` válidos
- **THEN** responde HTTP 200 con `items`, `total`, `page`, `size` y `pages`, del evento más reciente al más antiguo

#### Scenario: Usuario sin rol ADMIN
- **WHEN** un usuario autenticado sin rol `ADMIN` llama a `GET /eventos`
- **THEN** responde HTTP 403

#### Scenario: Página fuera de rango
- **WHEN** se solicita una `page` mayor que la última disponible
- **THEN** responde HTTP 422

#### Scenario: Tamaño de página fuera de rango
- **WHEN** se solicita `size=500` o `size=0`
- **THEN** responde HTTP 422

#### Scenario: Sin eventos
- **WHEN** la tabla está vacía
- **THEN** responde HTTP 200 con `items=[]`, `total=0`, `pages=1`
