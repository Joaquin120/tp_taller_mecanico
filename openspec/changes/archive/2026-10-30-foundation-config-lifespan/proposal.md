# Proposal

## Why
El proyecto requiere establecer su base arquitectónica inicial (Ejercicio 1 de la cátedra): una aplicación FastAPI asincrónica estructurada en capas, configuración tipada leída desde el entorno con `pydantic-settings`, gestión segura del ciclo de vida del motor de base de datos en `app.state` y endpoints de salud operacional (`/health/live` y `/health/ready`).

## What Changes
- **Scaffolding inicial**: Estructura de carpetas requerida (`app/core/`, `app/modules/health/`, `test/`).
- **Configuración (`app/core/config.py`)**: Clase `Settings` derivada de `BaseSettings` con `@computed_field` para la URL de PostgreSQL (`postgresql+asyncpg://...`), validando que secretos críticos (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`) no tengan valores por defecto y fallen al arrancar si faltan.
- **Persistencia base (`app/core/database.py`)**: Inicialización del motor asincrónico SQLAlchemy (`create_async_engine`) y fábrica de sesiones asincrónicas (`async_sessionmaker`), más la dependencia `get_session`.
- **Ciclo de vida ASGI (`main.py`)**: Gestor de contexto `lifespan` que inicializa el motor y la fábrica en `app.state`, precalcula el hash ficticio de bcrypt para protección contra timing attacks, y ejecuta `engine.dispose()` al cerrar la app.
- **Rutas de salud (`app/modules/health/router.py`)**:
  - `GET /health/live`: responde HTTP 200 inmediatamente sin consultar la base de datos.
  - `GET /health/ready`: ejecuta `SELECT 1` en PostgreSQL; responde 200 si la BD está lista o 503 Service Unavailable si falla.
- **Variables de entorno**: Archivo `env.example` con todas las variables requeridas sin secretos.
- **Dependencias**: Archivo `requirements.txt` con versiones fijadas compatibles.

## Capabilities

### New Capabilities
- `system-foundation`: Ciclo de vida de la aplicación, configuración tipada desde variables de entorno y verificación de salud operacional (liveness y readiness).

### Modified Capabilities
Ninguna (primer change del proyecto).

## Impact
- Establece los cimientos sobre los que construirán los siguientes changes (`C-02 domain-models-migrations-seed` y `C-03 core-uow-repository-contracts`).
- Define el contrato de variables de entorno y garantiza que la aplicación no arranque sin secretos definidos.
