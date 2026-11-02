# Spec Delta

## Purpose

Define y estandariza la suite de verificación end-to-end (E2E), el arnés de pruebas HTTP multi-sesión con REST Client, la validación de disparadores e integridad relacional en PostgreSQL, la comprobación de cero consultas N+1 y el manual operativo para la puesta en marcha reproducible del sistema.

## ADDED Requirements

### Requirement: Suite de pruebas HTTP de autenticacion y sesiones
The system SHALL provide a `test/auth.http` file that verifies test cases C-01 to C-09 in a reproducible manner, supporting concurrent sessions with `# @no-cookie-jar` and dynamic cookies per role.

#### Scenario: C-01 Parametro de ruta no entero
- **WHEN** un cliente autenticado envía una petición a un recurso con id no entero
- **THEN** el sistema responde con HTTP 422 sin ejecutar el handler de negocio

#### Scenario: C-02 Registro de cliente y unicidad
- **WHEN** se envía un registro válido, seguido de intentos con correo o documento repetidos
- **THEN** el primer intento responde 201 y los repetidos responden 409 con mensaje propio y sin filas huérfanas

#### Scenario: C-03 Cookie HttpOnly en login
- **WHEN** un usuario realiza login exitoso
- **THEN** el servidor responde 204 con Set-Cookie HttpOnly, SameSite=Lax, Max-Age y sin token en el cuerpo; peticiones sin cookie o con Bearer responden 401

#### Scenario: C-04 Timing safe en credenciales invalidas
- **WHEN** se prueba login con correo existente y clave errónea vs correo inexistente
- **THEN** ambos responden 401 con mensaje uniforme y tiempos de respuesta similares por hash ficticio

#### Scenario: C-05 Limite de intentos fallidos
- **WHEN** se ejecutan seis intentos fallidos consecutivos de login
- **THEN** el sexto intento responde 429 con cabecera Retry-After en pocos milisegundos y se auditan los fallos en intento_acceso

#### Scenario: C-06 Diferenciacion 401 contra 403 y privacidad
- **WHEN** se realizan peticiones sin rol requerido o un cliente intenta ver órdenes ajenas
- **THEN** el acceso sin rol responde 403, el cliente ve su orden (200) y la orden de un tercero responde 403

#### Scenario: C-07 Revocacion de rol en caliente
- **WHEN** el administrador revoca un rol a una sesión activa
- **THEN** la siguiente petición con esa cookie responde 403 evaluando la tabla de asignación en tiempo real

#### Scenario: C-08 Autoproteccion de cuenta administrador
- **WHEN** un administrador intenta revocar su propio rol de ADMIN
- **THEN** el sistema rechaza la petición con HTTP 409 protegiendo la existencia del rol administrativo

#### Scenario: C-09 Invocacion de cambio obligatorio de contrasena
- **WHEN** un usuario con cambio pendiente intenta operar sin actualizar su clave
- **THEN** el sistema bloquea con 403 salvo para /auth; tras actualizar clave, la cookie nueva opera (200) y la anterior se invalida inmediatamente (401)

### Requirement: Suite de pruebas HTTP de ordenes de trabajo
The system SHALL provide a `test/ordenes.http` file that verifies test cases C-10 to C-13 for work order lifecycle and atomic transactional stock updates.

#### Scenario: C-10 Alta de orden con multiples items
- **WHEN** se crea una orden con dos ítems con precios vigentes en el catálogo
- **THEN** responde 201 con precios congelados, total calculado en servidor e historial PENDIENTE; con repuesto inexistente responde 409 sin crear la orden

#### Scenario: C-11 Terminacion rechazada por stock insuficiente
- **WHEN** se intenta terminar una orden que solicita más unidades de las disponibles en stock
- **THEN** responde 409 y se produce rollback total, dejando intactos estado, stock, movimientos e historial

#### Scenario: C-12 Reposicion de stock y terminacion exitosa
- **WHEN** se repone el stock faltante y se reintenta terminar la orden
- **THEN** responde 200, descuenta stock, crea movimientos negativos, transiciona a TERMINADA y despacha aviso simulado en BackgroundTasks

#### Scenario: C-13 Cancelacion evaluando permisos antes que estado
- **WHEN** se solicita cancelación de órdenes
- **THEN** el dueño cancela su orden PENDIENTE (200), un cliente ajeno recibe 403 incluso sobre órdenes ajenas terminadas, y el actor autorizado sobre una orden terminada recibe 409

### Requirement: Suite de pruebas HTTP de repuestos y vehiculos
The system SHALL provide a `test/repuestos_vehiculos.http` file that verifies test cases C-16 to C-19 regarding catalog, stock, prices, vehicles, and pagination limits.

#### Scenario: C-16 Busqueda segura y restricciones de paginacion
- **WHEN** se envía búsqueda con payload SQL injection o parámetros de paginación inválidos
- **THEN** la búsqueda parametrizada no inyecta SQL devolviendo lista vacía; páginas o tamaños inválidos responden 422; y PATCH de stock responde 422

#### Scenario: C-17 Catalogo de estados de orden
- **WHEN** se consulta el catálogo de estados y se intentan filtros no permitidos
- **THEN** GET /estados-orden devuelve el catálogo ordenado por posición; sin sesión responde 401; y filtros con valores no soportados responden 422

#### Scenario: C-18 Auditoria historica de precios de repuestos
- **WHEN** se actualiza el precio de un repuesto mediante PATCH
- **THEN** se registra una nueva fila en el historial de precios con valores anterior y nuevo; si un segundo PATCH no altera el precio, no se inserta historial; recepción recibe 403

#### Scenario: C-19 Baja logica de vehiculo y reciclado de patente
- **WHEN** se da de baja lógica un vehículo sin órdenes y se registra otro vehículo con la misma patente
- **THEN** la baja responde 204 y el alta con la misma patente responde 201 gracias al índice único parcial; dos patentes vigentes iguales responden 409

### Requirement: Verificacion de disparadores PL/pgSQL y FK en base de datos
The system SHALL provide a `test/solo_agregado.sql` script verifying in PostgreSQL strict rejection of append-only modifications and foreign key enforcement (Case C-14).

#### Scenario: C-14 Rechazo de UPDATE y DELETE en tablas append-only y FK
- **WHEN** se intentan ejecutar sentencias UPDATE o DELETE sobre `historial_estado_orden`, `movimiento_stock`, o `historial_precio_repuesto`, o se inserta una orden con estado inexistente
- **THEN** PostgreSQL aborta las seis operaciones de modificación/borrado por disparador y la inserción inválida por violación de clave foránea

### Requirement: Verificacion de consultas SQL sin N+1
The system SHALL verify that work order detail queries maintain an invariant, fixed count of SQL statements regardless of the item count (Case C-15).

#### Scenario: C-15 Recuento invariante de consultas en detalle de orden
- **WHEN** se consulta el detalle de una orden con 2 ítems y el detalle de una orden con 4 ítems bajo logging de SQL (`SQL_ECHO=true`)
- **THEN** el número de sentencias SQL ejecutadas es idéntico para ambos casos gracias a la precarga anticipada

### Requirement: Documentacion de despliegue y variables de entorno
The system SHALL provide a complete `README.md` and `env.example` that allow any evaluator to deploy, migrate, seed, and run the service from scratch without ambiguity.

#### Scenario: Despliegue reproducible desde cero
- **WHEN** un evaluador sigue los pasos descritos en el `README.md` en un entorno limpio
- **THEN** la creación del entorno virtual, instalación de dependencias, configuración de variables, `alembic upgrade head`, `python seed.py` y levantamiento con Uvicorn se completan sin errores
