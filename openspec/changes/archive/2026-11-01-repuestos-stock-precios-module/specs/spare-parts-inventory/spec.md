# Spec Delta

## Purpose

Administra el catálogo de repuestos del taller: consulta con búsqueda y paginación, alta con stock inicial, reposición, actualización de precios con historial atómico y baja lógica, sin exponer escrituras sobre las tablas de sólo agregado.

## ADDED Requirements

### Requirement: Consulta paginada del catálogo
`GET /repuestos` SHALL devolver los repuestos vigentes (`borrado_en IS NULL`) en el envoltorio `{items, total, page, size, pages}`, ordenados por `codigo` ascendente. SHALL aceptar `q` como búsqueda parcial sin distinguir mayúsculas sobre `descripcion`, `page` desde 1 y `size` de 1 a 100. Una página fuera de rango SHALL responder 422.

#### Scenario: Listado paginado válido
- **WHEN** se solicita `GET /repuestos?page=1&size=20`
- **THEN** responde HTTP 200 con `items`, `total`, `page`, `size` y `pages` coherentes, ordenados por `codigo`

#### Scenario: Búsqueda por descripción
- **WHEN** se envía `q` con un fragmento de descripción en minúsculas
- **THEN** la respuesta sólo incluye repuestos cuya `descripcion` contiene ese fragmento sin distinguir mayúsculas

#### Scenario: Repuesto borrado no aparece
- **WHEN** un repuesto tiene `borrado_en` no nulo
- **THEN** no aparece en el listado ni se cuenta en `total`

#### Scenario: Página fuera de rango
- **WHEN** se solicita una `page` mayor que la última disponible
- **THEN** responde HTTP 422

### Requirement: Detalle de repuesto vigente
`GET /repuestos/{id}` SHALL devolver `id`, `codigo`, `descripcion`, `precio` y `stock` del repuesto vigente. SHALL responder 404 si el repuesto no existe o está borrado lógicamente.

#### Scenario: Detalle existente
- **WHEN** se consulta un repuesto vigente por su `id`
- **THEN** responde HTTP 200 con sus datos actuales

#### Scenario: Repuesto inexistente o borrado
- **WHEN** el `id` no corresponde a un repuesto vigente
- **THEN** responde HTTP 404

### Requirement: Alta con stock inicial y movimiento atómico
`POST /repuestos` SHALL crear el repuesto y, si `stock_inicial > 0`, el `movimiento_stock` de alta con el usuario autenticado, en un único UoW. `precio` SHALL ser mayor a 0 y `stock_inicial` mayor o igual a 0. Un `codigo` repetido entre repuestos vigentes SHALL responder 409. La respuesta SHALL ser 201 con el repuesto creado.

#### Scenario: Alta con stock inicial
- **WHEN** un ADMIN envía `codigo`, `descripcion`, `precio` y `stock_inicial` mayores a cero y válidos
- **THEN** responde HTTP 201 y existe un `movimiento_stock` de alta por esa cantidad y el usuario actor

#### Scenario: Alta con stock inicial cero
- **WHEN** un ADMIN envía `stock_inicial = 0`
- **THEN** responde HTTP 201, el repuesto queda con stock 0 y no se inserta movimiento

#### Scenario: Código duplicado entre vigentes
- **WHEN** el `codigo` ya pertenece a un repuesto vigente
- **THEN** responde HTTP 409 y no queda ninguna fila parcial

#### Scenario: Precio o stock inválidos
- **WHEN** `precio <= 0` o `stock_inicial < 0`
- **THEN** responde HTTP 422 sin crear el repuesto

#### Scenario: Código reutilizable tras una baja
- **WHEN** el `codigo` pertenece sólo a un repuesto borrado lógicamente
- **THEN** el alta responde HTTP 201 por el índice único parcial

### Requirement: Actualización de descripción y precio con historial
`PATCH /repuestos/{id}` SHALL permitir modificar `descripcion` y/o `precio`, exigiendo al menos uno. Si el `precio` difiere del vigente, SHALL insertar `historial_precio_repuesto` con precio anterior, nuevo, usuario y timestamp en el mismo UoW. Si es idéntico, NO SHALL insertar fila. SHALL responder 422 si el cuerpo incluye `stock` o un precio no positivo, y 404 si el repuesto no existe o está borrado.

#### Scenario: Cambio de precio con historial
- **WHEN** un ADMIN envía un `precio` distinto del vigente
- **THEN** responde HTTP 200, el precio queda actualizado y se inserta una fila con `precio_anterior` y `precio_nuevo`

#### Scenario: Precio idéntico no genera historial
- **WHEN** el `precio` enviado es igual al vigente
- **THEN** responde HTTP 200 y no se inserta ninguna fila en el historial

#### Scenario: Intento de modificar stock
- **WHEN** el cuerpo del PATCH incluye el campo `stock`
- **THEN** responde HTTP 422 por `extra="forbid"` y no se modifica nada

#### Scenario: Sólo cambia la descripción
- **WHEN** el PATCH envía únicamente una `descripcion` distinta
- **THEN** responde HTTP 200 sin insertar filas en el historial de precios

#### Scenario: Precio no positivo
- **WHEN** el `precio` enviado es menor o igual a cero
- **THEN** responde HTTP 422 sin modificar el repuesto

#### Scenario: Repuesto inexistente o borrado
- **WHEN** el `id` no corresponde a un repuesto vigente
- **THEN** responde HTTP 404

#### Scenario: Fallo de auditoría revierte el precio
- **WHEN** la inserción del historial falla dentro del UoW
- **THEN** la transacción revierte y el precio anterior permanece sin cambios

### Requirement: Reposición de stock atómica
`POST /repuestos/{id}/reponer` SHALL exigir `cantidad` entera mayor a 0, incrementar `stock` e insertar `movimiento_stock` con motivo de reposición y el usuario autenticado, dentro de un único UoW. SHALL responder 404 si el repuesto no existe o está borrado, y 422 si `cantidad` no es positiva.

#### Scenario: Reposición exitosa
- **WHEN** un ADMIN repone una cantidad positiva sobre un repuesto vigente
- **THEN** responde HTTP 200, el stock se incrementa en esa cantidad y se inserta el movimiento correspondiente

#### Scenario: Cantidad no positiva
- **WHEN** `cantidad` es 0 o negativa
- **THEN** responde HTTP 422 sin modificar el stock

#### Scenario: Repuesto inexistente o borrado
- **WHEN** el `id` no corresponde a un repuesto vigente
- **THEN** responde HTTP 404

#### Scenario: Fallo del movimiento revierte el incremento
- **WHEN** la inserción del movimiento falla dentro del UoW
- **THEN** la transacción revierte y el stock conserva su valor anterior

### Requirement: Baja lógica del repuesto
`DELETE /repuestos/{id}` SHALL marcar `borrado_en` sin eliminar la fila y responder 204. A partir de la baja, el repuesto NO SHALL aparecer en listado ni detalle y su `codigo` SHALL poder reutilizarse en un alta nueva. SHALL responder 404 si el repuesto no existe o ya está borrado.

#### Scenario: Baja exitosa
- **WHEN** un ADMIN elimina un repuesto vigente
- **THEN** responde HTTP 204, la fila conserva sus datos con `borrado_en` registrado y deja de aparecer en las consultas

#### Scenario: Segunda baja
- **WHEN** se intenta eliminar un repuesto ya borrado
- **THEN** responde HTTP 404

#### Scenario: Código liberado
- **WHEN** se da de baja un repuesto y se intenta un alta con el mismo `codigo`
- **THEN** el alta responde HTTP 201 sin conflicto

### Requirement: Historial de movimientos de stock
`GET /repuestos/{id}/movimientos` SHALL devolver el historial paginado de movimientos del repuesto, del más reciente al más antiguo, con `cantidad`, `motivo`, `cuando`, `usuario_id` y `orden_id` cuando exista. SHALL responder 404 si el repuesto no existe o está borrado.

#### Scenario: Historial de movimientos
- **WHEN** un ADMIN consulta los movimientos de un repuesto con alta y reposiciones
- **THEN** responde HTTP 200 con `{items, total, page, size, pages}` ordenado por `cuando` descendente

#### Scenario: Repuesto sin movimientos
- **WHEN** el repuesto existe pero no tiene movimientos
- **THEN** responde HTTP 200 con `items=[]` y `total=0`

#### Scenario: Repuesto inexistente o borrado
- **WHEN** el `id` no corresponde a un repuesto vigente
- **THEN** responde HTTP 404

### Requirement: Historial de precios
`GET /repuestos/{id}/precios` SHALL devolver el historial paginado de cambios de precio, del más reciente al más antiguo, con `precio_anterior`, `precio_nuevo`, `cuando` y `usuario_id`. SHALL responder 404 si el repuesto no existe o está borrado.

#### Scenario: Historial de precios
- **WHEN** un ADMIN consulta un repuesto con cambios de precio registrados
- **THEN** responde HTTP 200 con las filas ordenadas por `cuando` descendente

#### Scenario: Repuesto sin cambios de precio
- **WHEN** el repuesto existe pero nunca cambió de precio
- **THEN** responde HTTP 200 con `items=[]` y `total=0`

#### Scenario: Repuesto inexistente o borrado
- **WHEN** el `id` no corresponde a un repuesto vigente
- **THEN** responde HTTP 404

### Requirement: Stock de mutación controlada
El `stock` NO SHALL modificarse mediante `PATCH /repuestos/{id}`. Sólo SHALL cambiar por alta con stock inicial, reposición o terminación de orden. El stock persistido NO SHALL ser negativo y el precio NO SHALL ser menor o igual a cero; la base de datos SHALL rechazar ambos casos.

#### Scenario: PATCH no acepta stock
- **WHEN** se envía `stock` en el cuerpo de `PATCH /repuestos/{id}`
- **THEN** responde HTTP 422 y el stock permanece igual

#### Scenario: Stock no negativo
- **WHEN** una operación intentaría dejar `stock` negativo
- **THEN** la restricción CHECK de la base de datos rechaza la escritura y la API responde un error de negocio, no un 500

#### Scenario: Precio positivo
- **WHEN** una operación intentaría persistir `precio <= 0`
- **THEN** la restricción CHECK rechaza la escritura y la API responde 422

### Requirement: Inmutabilidad de las tablas de sólo agregado
`movimiento_stock` e `historial_precio_repuesto` SHALL ser de sólo agregado: el módulo NO SHALL exponer endpoints para modificarlas ni borrarlas, y la base de datos SHALL rechazar `UPDATE` y `DELETE` mediante triggers PL/pgSQL. Las inserciones dentro de un UoW SHALL seguir permitidas.

#### Scenario: Sin rutas de escritura sobre historiales
- **WHEN** se intenta un método de escritura sobre `/repuestos/{id}/movimientos` o `/repuestos/{id}/precios`
- **THEN** la API responde 405 y no muta datos

#### Scenario: Trigger rechaza modificación
- **WHEN** un proceso intenta `UPDATE` o `DELETE` directo sobre `movimiento_stock` o `historial_precio_repuesto`
- **THEN** el trigger de la base de datos interrumpe la operación con excepción

#### Scenario: Inserción permitida
- **WHEN** el servicio inserta un movimiento o una fila de historial dentro de su UoW
- **THEN** la inserción se confirma junto con el resto de la operación

### Requirement: Autorización por roles del catálogo
`GET /repuestos` y `GET /repuestos/{id}` SHALL estar disponibles para `ADMIN`, `RECEPCION` y `MECANICO`. Las mutaciones y las consultas de historiales SHALL exigir `ADMIN`. Un usuario `CLIENTE` SHALL recibir 403 y una petición sin sesión SHALL recibir 401.

#### Scenario: Personal consulta el catálogo
- **WHEN** un usuario con rol vigente `ADMIN`, `RECEPCION` o `MECANICO` consulta el listado o el detalle
- **THEN** responde HTTP 200 según el contrato

#### Scenario: Cliente sin acceso
- **WHEN** un usuario `CLIENTE` consulta el catálogo
- **THEN** responde HTTP 403

#### Scenario: Sin sesión
- **WHEN** se llama a cualquier ruta de repuestos sin cookie válida
- **THEN** responde HTTP 401

#### Scenario: Recepción intenta mutar
- **WHEN** un usuario `RECEPCION` intenta `POST`, `PATCH`, `DELETE` o reponer
- **THEN** responde HTTP 403 sin ejecutar el handler

### Requirement: Contratos de entrada estrictos
Todos los DTOs de entrada SHALL rechazar campos no declarados con 422 (`extra="forbid"`). Las respuestas NO SHALL exponer trazas ni detalles internos de PostgreSQL. `codigo` SHALL tener entre 1 y 50 caracteres y `descripcion` entre 1 y 255.

#### Scenario: Campo adicional rechazado
- **WHEN** un cuerpo incluye un campo no declarado en el contrato
- **THEN** responde HTTP 422 indicando campo adicional no permitido

#### Scenario: Error sin detalles internos
- **WHEN** se produce una violación de integridad
- **THEN** la respuesta sólo contiene un mensaje de negocio, sin SQL, constraint ni tabla

#### Scenario: Longitudes fuera de rango
- **WHEN** `codigo` o `descripcion` exceden su longitud máxima o quedan vacíos
- **THEN** responde HTTP 422 sin persistir
