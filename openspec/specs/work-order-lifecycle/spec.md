# work-order-lifecycle Specification

## Purpose
Define el ciclo de vida de las órdenes de trabajo del taller: alta en estado `PENDIENTE` con precios copiados y total calculado en el servidor, consulta con carga anticipada, inicio por mecánico, terminación atómica con descuento de stock, cancelación con evaluación de permisos previa al estado y consulta de órdenes propias del cliente.

## Requirements

### Requirement: Catálogo de estados de sólo lectura
El sistema SHALL exponer el catálogo `estado_orden` mediante `GET /estados-orden`, ordenado por `posicion` ascendente. La API NO SHALL ofrecer alta, modificación ni baja de estados, y el catálogo SHALL ser la única fuente válida de estados de una orden (RN-19).

#### Scenario: Listado ordenado por posición
- **WHEN** un usuario autenticado consulta `GET /estados-orden`
- **THEN** recibe HTTP 200 con la lista de estados ordenada por `posicion`, cada uno con `codigo`, `descripcion`, `posicion` y `es_final`

#### Scenario: Catálogo sin rutas de escritura
- **WHEN** se intenta `POST`, `PATCH` o `DELETE` sobre `/estados-orden` o `/estados-orden/{codigo}`
- **THEN** la API responde 404 o 405 y el catálogo no se modifica

#### Scenario: Sesión requerida
- **WHEN** se consulta `GET /estados-orden` sin sesión válida
- **THEN** responde HTTP 401

### Requirement: Alta de orden siempre en estado PENDIENTE
Toda orden creada con `POST /ordenes` SHALL nacer en estado `PENDIENTE`, sin mecánico asignado y con `desde_estado` nulo en su primera línea de historial. El cliente NO SHALL poder fijar el estado inicial ni el mecánico (RN-10, RN-11).

#### Scenario: Alta exitosa
- **WHEN** un `ADMIN` o `RECEPCION` envía `vehiculo_id`, `falla` y al menos un ítem válido
- **THEN** responde HTTP 201 con `estado = "PENDIENTE"`, `mecanico_id = null` y una línea de historial `desde_estado = null`, `hasta_estado = "PENDIENTE"`

#### Scenario: Estado o mecánico enviados por el cliente
- **WHEN** el payload incluye `estado`, `mecanico_id`, `total` o cualquier campo no declarado
- **THEN** responde HTTP 422 y no se crea la orden

#### Scenario: Catálogo de estados vacío
- **WHEN** se intenta crear una orden y la tabla `estado_orden` no tiene filas
- **THEN** responde HTTP 409 con un mensaje propio y no se crea ninguna fila

### Requirement: Precios copiados y total calculado en el servidor
Los ítems enviados SHALL contener sólo `repuesto_id` y `cantidad`. El servidor SHALL copiar el `precio` vigente de cada repuesto al `precio_unitario` del ítem y SHALL calcular `subtotal = precio_unitario × cantidad` y `total = Σ subtotal`. El precio y el total enviados por el cliente NO SHALL aceptarse (RN-10).

#### Scenario: Total calculado por el servidor
- **WHEN** se crea una orden con dos repuestos de precios vigentes conocidos
- **THEN** cada ítem guarda el precio vigente del repuesto y el `total` de la orden es la suma exacta de los subtotales, con dos decimales

#### Scenario: Precio o total en el payload
- **WHEN** un ítem incluye `precio_unitario`, `subtotal` o la orden incluye `total`
- **THEN** responde HTTP 422 y no se crea la orden

#### Scenario: Cambio de precio posterior
- **WHEN** el precio de un repuesto cambia después de creada la orden
- **THEN** el ítem conserva el `precio_unitario` copiado al momento del alta y el `total` de la orden no se recalcula

### Requirement: Validación de la composición de la orden
La orden SHALL tener al menos un ítem y NO SHALL repetir el mismo `repuesto_id`. Cada `cantidad` SHALL ser mayor a cero. El vehículo y cada repuesto SHALL existir y estar vigentes al momento del alta (RN-10).

#### Scenario: Lista de ítems vacía
- **WHEN** se envía `items: []`
- **THEN** responde HTTP 422 y no se crea la orden

#### Scenario: Repuesto repetido
- **WHEN** dos ítems referencian el mismo `repuesto_id`
- **THEN** responde HTTP 422 y no se crea la orden

#### Scenario: Cantidad no positiva
- **WHEN** un ítem envía `cantidad` igual a cero o negativa
- **THEN** responde HTTP 422 y no se crea la orden

#### Scenario: Vehículo inexistente o dado de baja
- **WHEN** el `vehiculo_id` no existe o está borrado lógicamente
- **THEN** responde HTTP 409 y no se crea la orden

#### Scenario: Repuesto inexistente o dado de baja
- **WHEN** algún `repuesto_id` no existe o está borrado lógicamente
- **THEN** responde HTTP 409 y no se crea la orden ni sus ítems

### Requirement: Consulta paginada de órdenes
El sistema SHALL listar órdenes con paginación estándar y filtro opcional por `estado` exacto. El listado SHALL ordenarse de la más reciente a la más antigua y SHALL rechazar páginas fuera de rango (RN-10).

#### Scenario: Listado sin filtro
- **WHEN** `ADMIN`, `RECEPCION` o `MECANICO` consulta `GET /ordenes`
- **THEN** recibe HTTP 200 con `{items, total, page, size, pages}` y las órdenes de la más reciente a la más antigua

#### Scenario: Filtro por estado
- **WHEN** se consulta `GET /ordenes?estado=EN_REPARACION`
- **THEN** sólo se devuelven órdenes en ese estado y el `total` refleja el filtro

#### Scenario: Estado inexistente en el catálogo
- **WHEN** se consulta con un `estado` que no pertenece al catálogo
- **THEN** responde HTTP 422

#### Scenario: Página fuera de rango
- **WHEN** se solicita una `page` mayor que el total de páginas
- **THEN** responde HTTP 422

### Requirement: Detalle con carga anticipada sin N+1
`GET /ordenes/{id}` SHALL devolver la orden con vehículo, cliente, ítems, repuestos e historial de estados en una cantidad de consultas independiente de la cantidad de ítems (cero N+1).

#### Scenario: Detalle completo
- **WHEN** un usuario autorizado consulta una orden existente
- **THEN** responde HTTP 200 con patente, nombre del cliente, falla, total, estado, mecánico, ítems con precio copiado e historial de estados

#### Scenario: Consultas constantes
- **WHEN** se consultan dos órdenes idénticas en estructura pero con 2 y con 4 ítems
- **THEN** el número de sentencias SQL del detalle es el mismo en ambos casos

#### Scenario: Orden inexistente
- **WHEN** se consulta un `id` que no existe
- **THEN** responde HTTP 404

#### Scenario: Cliente dueño del vehículo
- **WHEN** un `CLIENTE` consulta una orden de un vehículo propio
- **THEN** responde HTTP 200 con el detalle

#### Scenario: Cliente ajeno
- **WHEN** un `CLIENTE` consulta una orden de un vehículo de otro cliente
- **THEN** responde HTTP 403 sin revelar datos de la orden

### Requirement: Inicio de orden por el mecánico
`POST /ordenes/{id}/iniciar` SHALL permitir sólo a un usuario con rol `MECANICO` vigente, que queda autoasignado como `mecanico_id`, y SHALL pasar la orden de `PENDIENTE` a `EN_REPARACION` (RN-11).

#### Scenario: Inicio exitoso
- **WHEN** un `MECANICO` inicia una orden `PENDIENTE`
- **THEN** responde HTTP 200 con `estado = "EN_REPARACION"`, `mecanico_id` igual al actor y una nueva línea de historial

#### Scenario: Orden no pendiente
- **WHEN** se intenta iniciar una orden en `EN_REPARACION`, `TERMINADA` o `CANCELADA`
- **THEN** responde HTTP 409 sin modificar la orden

#### Scenario: Rol distinto de mecánico
- **WHEN** un `ADMIN`, `RECEPCION` o `CLIENTE` intenta iniciar una orden
- **THEN** responde HTTP 403

### Requirement: Terminación atómica con descuento de stock
`POST /ordenes/{id}/terminar` SHALL ejecutarse en un único Unit of Work atómico. Por cada ítem SHALL descontar `cantidad` del stock del repuesto e insertar un `movimiento_stock` con `cantidad` negativa, `orden_id` de la orden y actor responsable; luego SHALL pasar la orden a `TERMINADA` e insertar la línea de historial. Si algún repuesto no alcanza, NO SHALL persistirse ninguna de esas escrituras (RN-13).

#### Scenario: Terminación exitosa
- **WHEN** el mecánico asignado o un `ADMIN` termina una orden `EN_REPARACION` con stock suficiente
- **THEN** responde HTTP 200 con `estado = "TERMINADA"`, el stock de cada repuesto disminuye exactamente la cantidad del ítem y existe un movimiento negativo por ítem asociado a la orden

#### Scenario: Stock insuficiente revierte todo
- **WHEN** al menos un repuesto no tiene stock suficiente
- **THEN** responde HTTP 409 y ni el stock, ni los movimientos, ni el estado de la orden, ni el historial cambian

#### Scenario: Orden no iniciada
- **WHEN** se termina una orden `PENDIENTE`, `TERMINADA` o `CANCELADA`
- **THEN** responde HTTP 409 sin descontar stock

#### Scenario: Actor no autorizado
- **WHEN** un mecánico distinto del asignado, un `RECEPCION` o un `CLIENTE` intenta terminar la orden
- **THEN** responde HTTP 403 sin descontar stock

#### Scenario: Precio copiado se conserva al terminar
- **WHEN** el precio del repuesto cambió entre el alta y la terminación
- **THEN** el ítem mantiene el precio copiado y el total de la orden no se recalcula

### Requirement: Cancelación con permisos evaluados antes que el estado
`POST /ordenes/{id}/cancelar` SHALL evaluar primero la pertenencia del vehículo y los roles del actor, y sólo después el estado. Por eso un actor sin permiso SHALL recibir HTTP 403 aunque la orden no sea cancelable, y un actor autorizado SHALL recibir HTTP 409 si la orden no está `PENDIENTE`. La cancelación exitosa SHALL dejar la orden en `CANCELADA` con su línea de historial (RN-12).

#### Scenario: Cancelación por el dueño
- **WHEN** el `CLIENTE` dueño del vehículo cancela una orden `PENDIENTE`
- **THEN** responde HTTP 200 con `estado = "CANCELADA"` y una nueva línea de historial

#### Scenario: Cancelación por recepción o administrador
- **WHEN** un `RECEPCION` o `ADMIN` cancela una orden `PENDIENTE`
- **THEN** responde HTTP 200 con `estado = "CANCELADA"`

#### Scenario: Permiso evaluado antes que el estado
- **WHEN** un `CLIENTE` que no es dueño del vehículo intenta cancelar una orden `TERMINADA`
- **THEN** responde HTTP 403, no HTTP 409

#### Scenario: Orden no cancelable por un actor autorizado
- **WHEN** un actor autorizado intenta cancelar una orden `EN_REPARACION`, `TERMINADA` o ya `CANCELADA`
- **THEN** responde HTTP 409 y la orden no cambia

#### Scenario: Orden inexistente
- **WHEN** se intenta cancelar un `id` que no existe
- **THEN** responde HTTP 404

### Requirement: Consulta de órdenes propias del cliente
`GET /mis-ordenes` SHALL devolver únicamente las órdenes de los vehículos cuyo cliente está vinculado al usuario autenticado, con paginación estándar y sin exponer órdenes de otros clientes (RN-17).

#### Scenario: Cliente con órdenes propias
- **WHEN** un `CLIENTE` consulta `GET /mis-ordenes`
- **THEN** recibe HTTP 200 con sólo las órdenes de sus vehículos, de la más reciente a la más antigua

#### Scenario: Cliente sin órdenes
- **WHEN** un `CLIENTE` sin órdenes consulta `GET /mis-ordenes`
- **THEN** recibe HTTP 200 con una lista vacía y `total = 0`

#### Scenario: Órdenes de terceros excluidas
- **WHEN** existen órdenes de vehículos de otros clientes
- **THEN** ninguna aparece en la respuesta

#### Scenario: Sin sesión
- **WHEN** se consulta `GET /mis-ordenes` sin sesión válida
- **THEN** responde HTTP 401

### Requirement: Aviso simulado posterior al commit
Tras una terminación exitosa, el sistema SHALL agendar un aviso simulado al cliente que se ejecuta después de responder y NO SHALL ejecutarlo si la terminación falla o se revierte (Ej. 8).

#### Scenario: Aviso agendado tras el commit
- **WHEN** una orden se termina correctamente
- **THEN** la respuesta HTTP 200 se emite y luego se ejecuta el aviso simulado con una espera de 0.5 segundos y un registro de log

#### Scenario: Sin aviso cuando hay rollback
- **WHEN** la terminación falla por stock insuficiente
- **THEN** responde HTTP 409 y no se agenda ni ejecuta ningún aviso

### Requirement: Historial de estados de sólo agregado
`historial_estado_orden` SHALL ser de sólo agregado: la API NO SHALL exponer rutas que la modifiquen o borren, la base de datos SHALL rechazar `UPDATE` y `DELETE` mediante trigger PL/pgSQL y las inserciones dentro de un UoW SHALL seguir permitidas (RN-15).

#### Scenario: Sin rutas de escritura
- **WHEN** se intenta un método de escritura sobre el historial de una orden
- **THEN** la API responde 404 o 405 y no muta datos

#### Scenario: Trigger rechaza modificación
- **WHEN** un proceso intenta `UPDATE` o `DELETE` directo sobre `historial_estado_orden`
- **THEN** el trigger interrumpe la operación con excepción

#### Scenario: Inserción permitida
- **WHEN** el servicio inserta una línea de historial dentro de su Unit of Work
- **THEN** la inserción se confirma junto con el resto de la transacción

### Requirement: Autorización por roles de la API de órdenes
Cada endpoint de órdenes SHALL aplicar la matriz RBAC vigente consultada en la base de datos en cada petición: alta para `ADMIN`/`RECEPCION`, listado para `ADMIN`/`RECEPCION`/`MECANICO`, inicio sólo `MECANICO`, terminación del mecánico asignado o `ADMIN`, cancelación del dueño, `RECEPCION` o `ADMIN`, y consulta de estados y órdenes propias para todo usuario autenticado (RN-04, RN-12, RN-17).

#### Scenario: Recepción crea órdenes
- **WHEN** un `RECEPCION` con rol vigente crea una orden válida
- **THEN** responde HTTP 201

#### Scenario: Cliente intenta crear
- **WHEN** un `CLIENTE` intenta `POST /ordenes`
- **THEN** responde HTTP 403

#### Scenario: Rol revocado en la base
- **WHEN** un usuario con rol en el token pero revocado en `asignacion_rol` intenta una operación protegida
- **THEN** responde HTTP 403 aunque el JWT siga vigente

#### Scenario: Sin sesión
- **WHEN** se llama cualquier endpoint de órdenes sin cookie de sesión válida
- **THEN** responde HTTP 401

### Requirement: Contratos estrictos y errores sin detalles internos
Los DTO de entrada NO SHALL aceptar campos no declarados (`extra="forbid"`). Ningún error SHALL revelar nombres de constraints, SQL ni trazas internas, y ninguna entrada inválida SHALL terminar en HTTP 500 (RN-18).

#### Scenario: Campo adicional rechazado
- **WHEN** el payload de alta incluye un campo desconocido
- **THEN** responde HTTP 422 con un mensaje de validación que no expone la base de datos

#### Scenario: Error de integridad controlado
- **WHEN** una escritura viola una restricción de la base de datos
- **THEN** responde un código de negocio (400, 404, 409 o 422) con mensaje propio y sin detalles internos

#### Scenario: Longitudes y tipos inválidos
- **WHEN** `falla` excede 500 caracteres o un identificador no es entero
- **THEN** responde HTTP 422
