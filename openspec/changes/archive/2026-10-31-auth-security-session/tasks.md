# Tasks

## 1. Modelo `IntentoAcceso`

- [x] 1.1 Crear `app/models/intento_acceso.py` con el modelo SQLModel `IntentoAcceso` (tabla `intento_acceso`, columnas: `id UUID PK`, `email str`, `ip str`, `exitoso bool`, `creado_en datetime`). Verificar que la clase se importa sin error desde `app/models/__init__.py`.
- [x] 1.2 Escribir tests `test/test_intento_acceso_model.py` verificando que el modelo se instancia correctamente con los campos requeridos y que `creado_en` usa el default de `utcnow`. Todos los tests deben pasar.

## 2. Seguridad bcrypt (`app/core/security.py`)

- [x] 2.1 **[RED]** Escribir `test/test_security.py` con tests fallidos para: (a) `hash_password` retorna hash verificable, (b) `verify_password` retorna True con contraseña correcta, (c) `verify_password` retorna False con incorrecta, (d) contraseña > 72 bytes es truncada. Verificar que fallan con `ModuleNotFoundError` o `ImportError`.
- [x] 2.2 **[GREEN]** Crear `app/core/security.py` con `hash_password(plain: str) -> str` y `verify_password(plain: str, hashed: str) -> bool`, ambas `async`, usando `asyncio.to_thread` + `asyncio.Semaphore(MAX_CONCURRENT_BCRYPT=4)`, truncando a 72 bytes. Verificar que los 4 tests pasan.
- [x] 2.3 **[TRIANGULATE]** Agregar tests de casos borde: contraseña vacía hasheable, semáforo no bloquea dos llamadas concurrentes. Verificar que todos los tests de `test_security.py` pasan.

## 3. Dependencia de autenticación (`app/core/auth.py`)

- [x] 3.1 **[RED]** Escribir `test/test_auth_deps.py` con tests fallidos para `get_current_user`: cookie ausente → 401, JWT inválido → 401, JWT expirado → 401. Verificar que fallan.
- [x] 3.2 **[GREEN]** Crear `app/core/auth.py` con `get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> UsuarioActual`: lee cookie `access_token`, decodifica con PyJWT (`HS256`), consulta `asignacion_rol` para roles vigentes. Verificar que los tests pasan.
- [x] 3.3 **[TRIANGULATE]** Agregar tests: JWT válido con roles devuelve `UsuarioActual` correcto, rol revocado no aparece en la lista. Verificar todos los tests de `test_auth_deps.py` pasan.
- [x] 3.4 Implementar `require_roles(*roles: str)` que retorna una dependencia FastAPI que lanza 403 si el usuario no tiene ninguno de los roles requeridos. Verificar con tests en `test_auth_deps.py`.

## 4. Servicio de autenticación (`app/services/auth_service.py`)

- [x] 4.1 **[RED]** Escribir `test/test_auth_service.py` con tests fallidos para `registrar_cliente`: registro exitoso (retorna usuario), email duplicado (lanza excepción de conflicto), documento duplicado (lanza excepción de conflicto). Verificar que fallan.
- [x] 4.2 **[GREEN]** Implementar `AuthService.registrar_cliente(dto, uow)`: valida unicidad de email y documento, crea `usuario` + `AsignacionRol(rol=CLIENTE)` + `Cliente` en el UoW. Hashea contraseña con `hash_password`. Verificar que los tests pasan.
- [x] 4.3 **[RED]** Agregar tests fallidos para `login`: credenciales correctas emite JWT, credenciales incorrectas lanza 401, email inexistente tarda similar y lanza 401, rate-limit activo lanza 429. Verificar que fallan.
- [x] 4.4 **[GREEN]** Implementar `AuthService.login(email, password, ip, app_state, session_factory)`: conteo de fallos en sesión independiente, timing con `dummy_hash`, hash ficticio, emisión JWT con `sub=email, iat=now, exp=now+1800`. Registra intento en sesión independiente. Verificar que los tests pasan.
- [x] 4.5 **[TRIANGULATE]** Agregar tests: 5 fallos exactos activan el 429, login exitoso después de 4 fallos reinicia contador. Verificar todos los tests de `test_auth_service.py` pasan.

## 5. Router (`app/routers/auth.py`) y registro en `main.py`

- [x] 5.1 **[RED]** Escribir `test/test_auth_router.py` con tests de integración usando `AsyncClient` (httpx) para: `POST /auth/registro` exitoso → 201, email duplicado → 409, `POST /auth/login` exitoso → 200 + cookie, credenciales inválidas → 401, `POST /auth/logout` → 200 + cookie Max-Age=0, `GET /auth/yo` sin cookie → 401. Verificar que fallan por `404` (router no registrado).
- [x] 5.2 **[GREEN]** Crear `app/routers/auth.py` con los cuatro endpoints. Registrar el router en `app/main.py` con prefijo `/auth`. Añadir `dummy_hash` precalculado al Lifespan. Verificar que los tests del router pasan.
- [x] 5.3 **[TRIANGULATE]** Agregar tests: `GET /auth/yo` con cookie válida → 200 con email y roles, `POST /auth/login` 6 veces → 429 en el 6to. Verificar todos los tests de `test_auth_router.py` pasan.
- [x] 5.4 Verificar que la suite completa del proyecto (`pytest -vv`) pasa en verde sin regresiones.

## Workflow follow-up

- Archivar el change con `/opsx:archive auth-security-session` una vez que todos los tasks estén marcados `[x]`.
- Hacer commit: `git commit -m "feat(c-04): autenticacion segura, bcrypt off-loop, cookie httponly y endpoints auth"`.
- Push de la rama: `git push origin feature/c-03-c-04`.
