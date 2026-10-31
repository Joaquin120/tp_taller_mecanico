# Design

## Context

Ver `proposal.md - Why`. El proyecto ya dispone de `UnitOfWork`, `BaseRepository` y `BaseSchema` (C-03). La app usa FastAPI con routers asíncronos, SQLModel + asyncpg, PyJWT y bcrypt (presentes en `requirements.txt`). No existe aún ninguna capa de autenticación. El modelo `usuario` (tabla `usuario`) ya está definido en C-02 con columnas `email`, `password_hash`, `nombre`, `debe_cambiar_password`, `password_cambiada_en`; el modelo `asignacion_rol` ya contempla `rol`, `revocada_en` y `vence_en`.

## Goals / Non-Goals

**Goals:**
- Implementar `app/core/security.py` con hash/verify bcrypt estrictamente fuera del event loop (DD-03).
- Implementar `app/core/auth.py` con la dependencia `get_current_user` (cookie → JWT → roles en BD) y `require_roles`.
- Implementar `app/services/auth_service.py` con lógica de registro, login y consulta de sesión.
- Implementar `app/routers/auth.py` con los cuatro endpoints (`/registro`, `/login`, `/logout`, `/yo`).
- Registrar el hash ficticio precalculado en el Lifespan de la app (RN-09).
- Agregar el modelo `IntentoAcceso` y la tabla `intento_acceso`.
- Cubrir todo con TDD estricto: RED → GREEN → TRIANGULATE → REFACTOR.

**Non-Goals:**
- Cambio de contraseña (`POST /auth/cambiar-password`) — pertenece a C-05 o C-06.
- RBAC de gestión de roles (`POST /usuarios/{id}/roles`, etc.) — C-05.
- Refresh token — no contemplado en el TP.
- Bloqueo `SELECT FOR UPDATE` de concurrencia — SU-02.

## Decisions

### D-1: Semáforo global en `security.py`

`MAX_CONCURRENT_BCRYPT = 4` como constante. Se instancia `_bcrypt_semaphore = asyncio.Semaphore(MAX_CONCURRENT_BCRYPT)` a nivel de módulo (creación diferida al primer event loop). Ambas funciones `hash_password` y `verify_password` son `async` y usan `async with _bcrypt_semaphore: await asyncio.to_thread(...)`.

**Alternativa descartada:** `run_in_executor` con ThreadPoolExecutor — más complejo sin beneficio adicional; `asyncio.to_thread` es la forma idiomática en Python 3.9+.

### D-2: Hash ficticio precalculado en Lifespan

En `app/main.py`, el Lifespan genera `DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt())` y lo almacena en `app.state.dummy_hash`. El `auth_service` accede a él vía `request.app.state.dummy_hash` en el endpoint de login. Esto garantiza que el hash siempre existe y se calcula una sola vez.

**Alternativa descartada:** Hash hardcodeado en código — viola `no-secrets-in-repo` y sería predecible.

### D-3: `intento_acceso` en sesión independiente

El `auth_service.login` crea una segunda instancia de `AsyncSession` (directamente de `async_session_factory`, no del `UnitOfWork` principal) para insertar y hacer commit del intento antes de retornar. Esto cumple DD-04: el rollback del login fallido no afecta a `intento_acceso`.

**Alternativa descartada:** Compartir la sesión del UoW — haría imposible el conteo de fallos si el login revierte (RN-08).

### D-4: Dependencia `get_current_user`

Lee la cookie `access_token`, decodifica el JWT con `PyJWT` (`HS256`), extrae `sub` (email) y consulta `asignacion_rol` filtrando `revocada_en IS NULL AND (vence_en IS NULL OR vence_en > NOW())`. Retorna un objeto `UsuarioActual` con los roles frescos. Si la cookie falta o el JWT es inválido lanza `HTTPException(401)`.

**Alternativa descartada:** Leer roles solo del JWT — viola RN-04 (la revocación no tendría efecto inmediato).

### D-5: Ubicación del router

`app/routers/auth.py` con prefijo `/auth`. Sin autenticación en `/registro` y `/login` (abiertos). `/logout` y `/yo` requieren `Depends(get_current_user)`.

### D-6: Modelo `IntentoAcceso`

SQLModel puro (tabla `intento_acceso`) con columnas: `id UUID PK`, `email str`, `ip str`, `exitoso bool`, `creado_en datetime` (default `utcnow`). No tiene soft-delete ni audit trail extendido (los triggers de sólo-agregado aplican solo a las tablas declaradas en C-02).

## Risks / Trade-offs

- **[Riesgo] `asyncio.Semaphore` creado a nivel de módulo antes del event loop** → Mitigación: Python 3.10+ permite instanciar `Semaphore` sin event loop activo; se usa `asyncio.get_event_loop()` implícito en el primer uso.
- **[Trade-off] Sesión independiente para `intento_acceso` no pasa por `UnitOfWork`** → Aceptado por diseño (DD-04); no se puede modelar como un repositorio del UoW principal.
- **[Riesgo] Timing no perfectamente uniforme** → El hash ficticio reduce la diferencia a ruido de red; aceptado según RN-09.
- **[Trade-off] `MAX_CONCURRENT_BCRYPT = 4` fijo** → Configurable vía variable de entorno en el futuro; por ahora constante es suficiente para el TP.

## Migration Plan

1. Alembic autogenera la nueva migración a partir de `IntentoAcceso` (modelo nuevo). La tabla `intento_acceso` no tiene dependencias circulares con las tablas existentes.
2. Ejecutar `alembic upgrade head` antes de levantar la aplicación con este cambio.
3. **Rollback:** `alembic downgrade -1` elimina la tabla `intento_acceso`. No hay datos de negocio en ella que requieran migración inversa.
