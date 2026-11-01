# Proposal

## Why

C-04 dejó la autenticación operativa, pero el sistema todavía no puede autorizar por rol ni forzar el cambio de contraseña provisoria. Sin C-05 no existe el grupo protegido, no hay forma de administrar roles con vigencia, la revocación no surte efecto inmediato y las sesiones emitidas antes de un cambio de contraseña siguen siendo válidas. Esto bloquea todos los módulos de negocio (C-06 en adelante) y los casos de cátedra C-07, C-08 y C-09.

## What Changes

- Montar dos grupos de rutas en `main.py`: Abierto (`/health/*`, `/auth/*`) y Protegido, con una dependencia única que exige sesión válida y bloquea con **403 toda ruta del grupo** cuando `debe_cambiar_password=True` (RN-06).
- Implementar `POST /auth/cambiar-password`: verifica la contraseña actual fuera del event loop, hashea la nueva antes de abrir el UoW, apaga la bandera, registra `password_cambiada_en` con un único timestamp de aplicación y emite una cookie nueva.
- Invalidar sesiones previas comparando `iat` contra `password_cambiada_en` **sin truncar**: un token con `iat` estrictamente anterior da 401; el token nuevo, emitido con el mismo timestamp del cambio, es válido (RN-07).
- Agregar autorización `requiere_rol(...)` sobre roles vigentes en `asignacion_rol` en cada petición (RN-04) y las rutas ADMIN de personal: `POST /usuarios`, `GET /usuarios/{id}/roles`, `POST /usuarios/{id}/roles`, `DELETE /usuarios/{id}/roles/{rol}`.
- Alta de personal con contraseña provisoria y `debe_cambiar_password=True`; asignación con vencimiento opcional con zona horaria y futuro (422 si no cumple); reasignación de un rol vencido que cierra la fila anterior y abre una nueva en el mismo UoW; revocación sin borrar filas.
- Autoprotección: 409 si un administrador se revoca su propio `ADMIN` o si la operación dejaría al sistema sin administradores vigentes (RN-05).
- Registrar en `evento_seguridad` las altas, asignaciones, revocaciones y cambios de contraseña con `actor` textual, y exponer `GET /eventos` paginado para ADMIN.
- Traducir `IntegrityError` en un handler global: sólo restricciones conocidas a 409/422/400, sin exponer nombres de constraints, SQL ni trazas de PostgreSQL (RN-18).
- **BREAKING**: los contratos que reciben contraseñas rechazan con 422 las entradas de más de 72 **bytes** UTF-8, en lugar de truncarlas silenciosamente.

## Capabilities

### New Capabilities

- `authorization-rbac`: grupo protegido, autorización por roles vigentes en base de datos, gestión de asignaciones con vigencia, autoprotección de administradores y alta de personal.
- `security-audit`: registro append-only de eventos de seguridad y consulta paginada de la auditoría para ADMIN.
- `api-error-handling`: traducción de errores de integridad de la base a respuestas HTTP de negocio sin exponer detalles internos.

### Modified Capabilities

- `auth-session`: se agrega el cambio de contraseña autenticado, la invalidación de sesiones por `iat`/`password_cambiada_en`, el rechazo de contraseñas de más de 72 bytes en contrato y se corrige el cierre de sesión para que sea abierto e idempotente.

## Impact

- Código: `app/core/security.py`, `app/core/auth.py`, `app/core/dependencies.py`, `main.py`, `app/modules/usuarios/{schemas,repository,service,router,unit_of_work}.py`.
- API: nuevos endpoints de personal, roles y eventos; nuevo 403 por cambio de contraseña pendiente; nuevo 422 por límite de 72 bytes; `/auth/logout` deja de exigir sesión.
- Base de datos: sin migraciones; `password_cambiada_en`, `asignacion_rol` y `evento_seguridad` ya existen. Se apoya en el índice único parcial `uq_asignacion_rol_activa`.
- Pruebas: se extienden `test_auth_deps.py`, `test_auth_service.py`, `test_schemas.py` y se agregan pruebas de personal, roles, eventos y handler de integridad.
