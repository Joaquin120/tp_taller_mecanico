# Actores y Roles

## Actores del sistema

| Actor | Descripción | Forma de interacción |
| :--- | :--- | :--- |
| **Administrador** | Responsable máximo del taller y de la plataforma. | Autenticado con rol `ADMIN`. Acceso total al catálogo, personal, auditoría y acciones de contingencia. |
| **Recepción** | Encargado del trato con clientes y apertura de órdenes. | Autenticado con rol `RECEPCION`. Da de alta clientes, vehículos y abre o cancela órdenes. |
| **Mecánico** | Técnico encargado de las reparaciones físicas. | Autenticado con rol `MECANICO`. Consulta órdenes pendientes, las inicia asignándose la orden y las termina descontando repuestos. |
| **Cliente** | Propietario del vehículo que requiere servicio. | Autenticado con rol `CLIENTE`. Se registra por la web, consulta sus vehículos (`/mis-vehiculos`), órdenes (`/mis-ordenes`) y puede cancelar sus órdenes pendientes. |
| **SISTEMA** | Entidad de software abstracta para auditoría. | Actor de texto `"SISTEMA"` registrado en `evento_seguridad` durante la siembra de datos (`seed.py`). |

## Matriz RBAC de Permisos

Los roles no se guardan como columna en la tabla `usuario` ni se confían ciegamente desde el token JWT. La autorización se verifica **en cada petición** consultando en la base de datos las filas de `asignacion_rol` vigentes (`revocada_en IS NULL AND (vence_en IS NULL OR vence_en > NOW())`).

| Recurso / Acción | ADMIN | RECEPCION | MECANICO | CLIENTE | Anónimo |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `GET /health/*` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `POST /auth/registro` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `POST /auth/login` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `POST /auth/logout` | ✓ | ✓ | ✓ | ✓ | - |
| `GET /auth/yo` | ✓ | ✓ | ✓ | ✓ | - |
| `POST /auth/cambiar-password` | ✓ | ✓ | ✓ | ✓ | - |
| `POST /usuarios` (alta personal) | ✓ | - | - | - | - |
| `GET /usuarios/{id}/roles` | ✓ | - | - | - | - |
| `POST /usuarios/{id}/roles` | ✓ | - | - | - | - |
| `DELETE /usuarios/{id}/roles/{rol}` | ✓ | - | - | - | - |
| `GET /eventos` | ✓ | - | - | - | - |
| `POST /clientes` | ✓ | ✓ | - | - | - |
| `GET /clientes/{id}` | ✓ | ✓ | - | - | - |
| `POST /clientes/{id}/vehiculos` | ✓ | ✓ | - | - | - |
| `DELETE /vehiculos/{id}` | ✓ | ✓ | - | - | - |
| `GET /mis-vehiculos` | ✓ | ✓ | ✓ | ✓ (propios) | - |
| `GET /repuestos` (listado y detalle) | ✓ | ✓ | ✓ | - | - |
| `POST /repuestos` (alta con stock) | ✓ | - | - | - | - |
| `PATCH /repuestos/{id}` (desc/precio)| ✓ | - | - | - | - |
| `DELETE /repuestos/{id}` | ✓ | - | - | - | - |
| `POST /repuestos/{id}/reponer` | ✓ | - | - | - | - |
| `GET /repuestos/{id}/movimientos` | ✓ | - | - | - | - |
| `GET /repuestos/{id}/precios` | ✓ | - | - | - | - |
| `POST /ordenes` | ✓ | ✓ | - | - | - |
| `GET /ordenes` (listado) | ✓ | ✓ | ✓ | - | - |
| `GET /ordenes/{id}` | ✓ | ✓ | ✓ | Solo si es dueño | - |
| `POST /ordenes/{id}/iniciar` | - | - | ✓ | - | - |
| `POST /ordenes/{id}/terminar` | ✓ | - | Solo si está asignado | - | - |
| `POST /ordenes/{id}/cancelar` | ✓ | ✓ | - | Solo si es dueño | - |
| `GET /estados-orden` | ✓ | ✓ | ✓ | ✓ | - |
| `GET /mis-ordenes` | ✓ | ✓ | ✓ | ✓ (propias) | - |

## Reglas de Autoprotección y Gobernanza de Roles
- **RN-03:** Un usuario tiene a lo sumo una asignación abierta por rol (`(usuario_id, rol) WHERE revocada_en IS NULL`).
- **RN-04:** La autorización consulta los roles vigentes en la base en cada request. Revocar un rol surte efecto de inmediato, sin esperar la expiración del JWT.
- **RN-05 (Autoprotección):** Un administrador no puede revocarse a sí mismo el rol `ADMIN`. Además, el sistema impide cualquier operación que deje al taller sin al menos un `ADMIN` vigente activo (responde HTTP 409).
- **Vencimientos de roles:** Si un rol se asigna con vencimiento, el campo `vence_en` debe ser estrictamente en el futuro y con zona horaria informada (de lo contrario responde HTTP 422).
- **Asignación sin borrado:** Revocar un rol nunca borra la fila de la tabla; establece `revocada_en = NOW()`.
