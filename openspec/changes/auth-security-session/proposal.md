# Proposal

## Why

El sistema necesita un mecanismo de autenticación seguro antes de poder exponer cualquier endpoint protegido. Sin este cambio no existe forma de identificar al usuario que realiza cada petición, de verificar sus credenciales de manera segura, ni de establecer y revocar su sesión, bloqueando la implementación de toda la capa RBAC y los endpoints de negocio.

## What Changes

- **Nuevo módulo `app/core/security.py`**: funciones `hash_password` y `verify_password` basadas en `bcrypt`, ejecutadas fuera del event loop mediante `asyncio.to_thread` y acotadas por `asyncio.Semaphore(MAX_CONCURRENT_BCRYPT)`. La entrada se trunca a 72 bytes antes de cualquier operación (DD-03).
- **Nuevo router `app/routers/auth.py`** con los endpoints:
  - `POST /auth/registro` — auto-registro atómico: crea `usuario` + rol `CLIENTE` + `cliente` en un único UoW (RN-02). Retorna 201 o 409.
  - `POST /auth/login` — verifica rate-limit (5 fallos / 60 s por email+IP, RN-08), timing uniforme contra hash ficticio si el email no existe (RN-09), emite JWT en cookie `HttpOnly; SameSite=Lax; Max-Age=1800`. El intento se registra en sesión/transacción independiente (DD-04).
  - `POST /auth/logout` — elimina la cookie de sesión con `Max-Age=0`.
  - `GET /auth/yo` — devuelve el usuario autenticado con roles frescos de la BD y los roles del token.
- **Nuevo servicio `app/services/auth_service.py`**: orquesta la lógica de registro, login, logout y consulta de sesión actual. Toda operación I/O usa la capa UoW/Repository.
- **Nuevo módulo `app/core/auth.py`** (dependencias FastAPI): `get_current_user` que lee la cookie, valida el JWT (PyJWT), y consulta roles vigentes en `asignacion_rol` (RN-04). Incluye `require_roles(*roles)` para autorización por rol.
- **Nuevo modelo SQLModel `app/models/intento_acceso.py`** (o en el módulo de modelos existente): tabla `intento_acceso` con `email`, `ip`, `exitoso`, `creado_en`.
- **Hash ficticio precalculado en el Lifespan** de la aplicación para garantizar timing uniforme (RN-09).
- **Tests de integración** (async, con `pytest-asyncio`) para los cuatro endpoints cubriendo: registro exitoso, email duplicado (409), login exitoso (cookie presente), credenciales inválidas (401), rate-limit (429), logout y `/yo` autenticado y no autenticado (401).

## Capabilities

### New Capabilities

- `auth-session`: Autenticación de usuarios con bcrypt, emisión/revocación de sesión JWT en cookie HttpOnly y registro de intentos de acceso independiente.
- `user-registration`: Auto-registro de cliente en un único UoW atómico con creación de usuario, rol CLIENTE y ficha de cliente.

### Modified Capabilities

_(ninguna — las specs existentes no tienen requisitos de autenticación ni sesión)_

## Impact

- **Nuevos archivos**: `app/core/security.py`, `app/core/auth.py`, `app/routers/auth.py`, `app/services/auth_service.py`, y extensión del módulo de modelos para `intento_acceso`.
- **`app/main.py`**: inclusión del router `/auth` y precálculo del hash ficticio en el Lifespan.
- **Dependencias ya instaladas**: `bcrypt`, `PyJWT`, `fastapi`, `sqlmodel`, `asyncpg` (presentes en `requirements.txt`).
- **Tests**: nuevos archivos en `test/` que corren con `pytest-asyncio`.
- **Sin cambios en esquema de BD** de las tablas existentes; sólo se agrega la tabla `intento_acceso` como modelo nuevo.
