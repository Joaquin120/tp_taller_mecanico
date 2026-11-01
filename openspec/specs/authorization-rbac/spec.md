# authorization-rbac Specification

## Purpose

Define qué rutas puede operar cada usuario según sus roles vigentes en la base y protege al sistema de operar con una contraseña provisoria pendiente o de quedar sin administradores.

## Requirements

### Requirement: Grupo protegido con sesión y cambio de contraseña resuelto
Toda ruta del grupo Protegido SHALL exigir una sesión válida y SHALL responder 403 cuando el usuario tenga `debe_cambiar_password=True`. El bloqueo SHALL aplicarse a todos los métodos, incluidos GET, de modo que sólo `/health/*` y `/auth/*` queden accesibles mientras la bandera esté activa (RN-06).

#### Scenario: Sin sesión no ejecuta el handler
- **WHEN** se llama a cualquier ruta del grupo Protegido sin cookie válida
- **THEN** la respuesta es HTTP 401 y el handler no se ejecuta

#### Scenario: Cambio pendiente bloquea lecturas
- **WHEN** un usuario con `debe_cambiar_password=True` llama a `GET /eventos`
- **THEN** la respuesta es HTTP 403

#### Scenario: Cambio pendiente bloquea mutaciones
- **WHEN** un usuario con `debe_cambiar_password=True` llama a `POST /usuarios`
- **THEN** la respuesta es HTTP 403

#### Scenario: Cambio resuelto habilita el grupo
- **WHEN** el usuario cambia su contraseña y reintenta la misma ruta protegida
- **THEN** la respuesta deja de ser 403 y la ruta se ejecuta según sus roles

### Requirement: Autorización por roles vigentes en base de datos
Cada ruta protegida SHALL declarar los roles habilitados. La decisión SHALL consultar en cada petición las asignaciones vigentes de `asignacion_rol` (`revocada_en IS NULL` y sin vencer) y los roles del JWT NO SHALL otorgar permisos por sí solos (RN-04).

#### Scenario: Revocación con sesión abierta
- **WHEN** se revoca un rol y el usuario reintenta con la misma cookie
- **THEN** la petición siguiente responde HTTP 403 sin esperar el vencimiento del token

#### Scenario: Rol del token no vigente en la base
- **WHEN** el token informa `ADMIN` pero la base sólo registra `CLIENTE` vigente
- **THEN** una ruta que exige `ADMIN` responde HTTP 403

#### Scenario: Rol vigente habilita la ruta
- **WHEN** el usuario tiene el rol requerido vigente en la base
- **THEN** la ruta protegida se ejecuta y responde según su contrato

### Requirement: Alta de personal con contraseña provisoria
`POST /usuarios` SHALL crear en un único UoW un usuario activo con `debe_cambiar_password=True`, una asignación de rol de personal vigente y un evento de auditoría. La contraseña SHALL hashearse antes de abrir la transacción y el contrato SHALL rechazar con 422 las entradas de menos de 6 caracteres o más de 72 bytes UTF-8.

#### Scenario: Alta exitosa
- **WHEN** un ADMIN envía `POST /usuarios` con email, nombre, contraseña y rol de personal válidos
- **THEN** responde HTTP 201, el usuario queda con la bandera activa, su rol vigente y el evento de alta registrado

#### Scenario: Email repetido
- **WHEN** el email ya existe
- **THEN** responde HTTP 409 y no quedan filas de usuario, rol ni evento creadas por esa petición

#### Scenario: Contraseña de más de 72 bytes
- **WHEN** la contraseña provisoria supera 72 bytes UTF-8
- **THEN** responde HTTP 422 sin crear filas

#### Scenario: Rol fuera del catálogo de personal
- **WHEN** el rol enviado no es `ADMIN`, `RECEPCION` ni `MECANICO`
- **THEN** responde HTTP 422

### Requirement: Asignación de roles con vigencia
`POST /usuarios/{id}/roles` SHALL crear una asignación abierta para un rol del catálogo. `vence_en` SHALL ser opcional, con zona horaria y posterior al momento de la solicitud; una fecha sin zona o pasada SHALL responder 422. Si ya existe una asignación abierta vigente para ese rol SHALL responder 409 (RN-03).

#### Scenario: Asignación válida
- **WHEN** un ADMIN asigna un rol con vencimiento futuro y con zona horaria, o sin vencimiento
- **THEN** responde HTTP 201 con la asignación abierta

#### Scenario: Rol ya vigente
- **WHEN** el usuario ya tiene una asignación abierta y vigente para ese rol
- **THEN** responde HTTP 409 sin crear una segunda fila abierta

#### Scenario: Vencimiento sin zona horaria
- **WHEN** `vence_en` llega sin información de zona horaria
- **THEN** responde HTTP 422

#### Scenario: Vencimiento en el pasado
- **WHEN** `vence_en` es anterior o igual al momento de la solicitud
- **THEN** responde HTTP 422

#### Scenario: Usuario inexistente
- **WHEN** el `{id}` de la ruta no corresponde a un usuario
- **THEN** responde HTTP 404

### Requirement: Reasignación transaccional de un rol vencido
Si existe una asignación abierta pero vencida, el sistema SHALL cerrarla con `revocada_en` y crear la nueva en el mismo UoW. El índice único parcial SHALL impedir dos asignaciones abiertas para el mismo `(usuario_id, rol)`; ante solicitudes concurrentes, una SHALL completarse con 201 y la otra con 409, sin filas parciales.

#### Scenario: Rol vencido se reemplaza
- **WHEN** se asigna un rol cuya única fila abierta está vencida
- **THEN** responde HTTP 201, la fila anterior queda con `revocada_en` y existe exactamente una fila abierta para ese rol

#### Scenario: Solicitudes concurrentes
- **WHEN** dos peticiones intentan asignar el mismo rol al mismo usuario a la vez
- **THEN** exactamente una responde HTTP 201, la otra responde HTTP 409 y sólo queda una fila abierta

#### Scenario: Fallo de inserción revierte el cierre
- **WHEN** el cierre de la fila vencida se ejecuta pero la inserción de la nueva falla
- **THEN** la transacción revierte y la fila anterior permanece abierta como estaba

### Requirement: Revocación de roles sin borrar historial
`DELETE /usuarios/{id}/roles/{rol}` SHALL revocar la asignación abierta escribiendo `revocada_en`, sin borrar la fila. SHALL responder 404 si el usuario no existe o no hay asignación abierta para ese rol —incluido un rol fuera del catálogo— y 200 cuando revoca.

#### Scenario: Revocación exitosa
- **WHEN** un ADMIN revoca un rol con asignación abierta
- **THEN** responde HTTP 200 y la fila sigue existiendo con `revocada_en` registrado

#### Scenario: Rol fuera del catálogo
- **WHEN** el `{rol}` de la ruta no es uno de los cuatro roles del catálogo
- **THEN** responde HTTP 404

#### Scenario: Sin asignación abierta
- **WHEN** el usuario no tiene una asignación abierta para ese rol
- **THEN** responde HTTP 404

#### Scenario: Segunda revocación
- **WHEN** se intenta revocar un rol ya revocado
- **THEN** responde HTTP 404

### Requirement: Autoprotección de administradores
Un administrador NO SHALL poder revocarse su propio rol `ADMIN`. El sistema SHALL responder 409 cuando la revocación dejaría cero administradores vigentes, contando sólo asignaciones no revocadas y no vencidas (RN-05).

#### Scenario: Auto-revocación
- **WHEN** un ADMIN intenta revocar su propio rol `ADMIN`
- **THEN** responde HTTP 409 y su asignación permanece abierta

#### Scenario: Revocar al último administrador
- **WHEN** un ADMIN intenta revocar el `ADMIN` de otro usuario y no queda ningún otro administrador vigente
- **THEN** responde HTTP 409

#### Scenario: Existe otro administrador vigente
- **WHEN** un ADMIN revoca el `ADMIN` de otro usuario y queda al menos un administrador vigente distinto
- **THEN** responde HTTP 200

#### Scenario: Administrador vencido no cuenta
- **WHEN** el único otro administrador tiene su asignación vencida
- **THEN** la revocación responde HTTP 409 por dejar cero administradores vigentes

### Requirement: Consulta del historial de roles
`GET /usuarios/{id}/roles` SHALL devolver todas las asignaciones del usuario, incluidas vencidas y revocadas, con `rol`, `desde`, `vence_en`, `revocada_en` e indicador `vigente`. SHALL responder 404 si el usuario no existe y 200 con lista vacía si existe sin asignaciones.

#### Scenario: Historial completo
- **WHEN** un ADMIN consulta un usuario con asignaciones vigentes y revocadas
- **THEN** responde HTTP 200 con todas las filas y `vigente=false` en las revocadas o vencidas

#### Scenario: Usuario sin roles
- **WHEN** el usuario existe pero no tiene asignaciones
- **THEN** responde HTTP 200 con una lista vacía

#### Scenario: Usuario inexistente
- **WHEN** el `{id}` no corresponde a un usuario
- **THEN** responde HTTP 404
