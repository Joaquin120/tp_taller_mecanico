# Tasks

## 1. Setup y Dependencias

- [x] 1.1 Crear `requirements.txt` con FastAPI, uvicorn, pydantic-settings, sqlalchemy, asyncpg, sqlmodel, bcrypt y pyjwt, y verificar instalación con `pip install -r requirements.txt`
- [x] 1.2 Crear `env.example` con todas las variables requeridas sin secretos y verificar estructura de directorios (`app/core`, `app/modules/health`)

## 2. Configuración y Base de Datos

- [x] 2.1 Implementar `app/core/config.py` con `Settings(BaseSettings)` y `@computed_field` para `database_url`, verificando que falle si falta `POSTGRES_PASSWORD` o `JWT_SECRET_KEY`
- [x] 2.2 Implementar `app/core/database.py` con funciones `crear_motor`, `crear_fabrica_sesiones` y la dependencia `get_session` con `expire_on_commit=False`

## 3. Lifespan y Endpoints de Salud

- [x] 3.1 Implementar `app/modules/health/router.py` con `GET /health/live` (200 OK) y `GET /health/ready` (`SELECT 1`, responde 200 o 503)
- [x] 3.2 Implementar `main.py` con `lifespan` que inicialice `app.state.engine`, `app.state.session_factory`, precalcule `app.state.dummy_hash` y ejecute `dispose()` al cerrar
- [x] 3.3 Escribir pruebas unitarias/integración en `test/test_health.py` verificando `/health/live` y `/health/ready` con mock o conexión de base de datos

## Workflow follow-up

- Verificar `openspec validate` sobre el change.
- Proceder al apply workflow tras aprobación del usuario.
