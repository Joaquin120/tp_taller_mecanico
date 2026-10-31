# Design

## Context
Ver `proposal.md` para motivación y justificación general. El proyecto sigue una arquitectura en 6 capas donde los recursos de conexión compartidos no deben inicializarse a nivel de importación de módulo (anti-patrón EA-08), sino explícitamente en el lifespan de FastAPI cuando el event loop ya está activo.

## Goals / Non-Goals

**Goals:**
- Configuración estricta tipada con `pydantic-settings.BaseSettings` leyendo de entorno o `.env`.
- Cálculo dinámico de `DATABASE_URL` mediante `@computed_field`.
- Inicialización del motor asincrónico `create_async_engine` y fábrica `async_sessionmaker` en `app.state` dentro de `lifespan(app: FastAPI)`.
- Dependencia `get_session` que toma la fábrica desde `request.app.state.session_factory` y entrega una sesión con `expire_on_commit=False`, cerrándola con `session.close()` al finalizar.
- Pre-cálculo del hash ficticio de bcrypt en `app.state.dummy_hash` para el futuro login uniforme anti-timing.
- Cierre limpio del pool con `await app.state.engine.dispose()` al terminar el lifespan.
- Endpoints en `app/modules/health/router.py`:
  - `GET /health/live`: responde 200 OK inmediatamente.
  - `GET /health/ready`: ejecuta `SELECT 1` y devuelve 200 o 503 si falla.

**Non-Goals:**
- No se definen modelos de entidades de negocio en este change (corresponde a `C-02`).
- No se implementa la autenticación JWT ni bcrypt completo (corresponde a `C-04`).
- No se configuran migraciones de Alembic en este change (corresponde a `C-02`).

## Decisions

### DD-01: Variables de entorno separadas para construir la URL de base de datos
- **Decisión:** Leer `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` y `POSTGRES_DB` de forma individual y componer `DATABASE_URL` con `@computed_field`.
- **Razón:** La consigna exige expresamente que la dirección de la base se arme con variables sueltas y que `POSTGRES_PASSWORD` no tenga valor por defecto.
- **Alternativas consideradas:** Variable única `DATABASE_URL`. Descartada por requerimiento de la consigna.

### DD-02: Recursos de base de datos en `app.state` dentro del Lifespan
- **Decisión:** Crear `engine` y `session_factory` dentro de `async def lifespan(app: FastAPI)` y almacenarlos en `app.state`.
- **Razón:** Crear el motor al importar módulos genera que se vincule a un bucle de eventos previo o inexistente, provocando fallos sutiles al levantar el servidor o ejecutar tests (EA-08, sección 1.9).
- **Alternativas consideradas:** Variables globales en `app/core/database.py`. Descartadas por riesgo de inicialización fuera del bucle.

### DD-03: `get_session` con `expire_on_commit=False`
- **Decisión:** Configurar la fábrica de sesiones con `expire_on_commit=False`.
- **Razón:** Evita que SQLAlchemy intente emitir consultas de recarga perezosa (lazy reload) al acceder a atributos de modelos después de un `flush()` o `commit()`, lo cual rompe en entornos asincrónicos.

## Risks / Trade-offs

- **[Riesgo: Falta de variables en testing local]** → Proveer un archivo `env.example` claro y exhaustivo para que el desarrollador pueda copiar a `.env` con un comando.
- **[Riesgo: Base de datos no disponible durante readiness]** → Manejar cualquier excepción de conexión en `/health/ready` capturando `Exception` y devolviendo HTTP 503 con código JSON controlado, sin arrojar HTTP 500 no capturado.
