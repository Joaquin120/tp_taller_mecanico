# Spec Delta

## Purpose
Provee la inicialización del ciclo de vida ASGI, configuración tipada desde variables de entorno y endpoints de salud operacional para la API del taller mecánico.

## ADDED Requirements

### Requirement: Typed Environment Configuration
The system SHALL load application configuration using `pydantic-settings` and fail on startup if mandatory variables or secrets without defaults are missing.

#### Scenario: Missing database password stops application
- **WHEN** la aplicación arranca sin la variable de entorno `POSTGRES_PASSWORD`
- **THEN** el sistema lanza un error de validación de configuración y la aplicación no arranca

#### Scenario: Dynamic database URL computation
- **WHEN** se proveen las variables `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` y `POSTGRES_DB`
- **THEN** el sistema calcula la URL asincrónica `postgresql+asyncpg://<user>:<password>@<host>:<port>/<db>`

### Requirement: Lifespan Resource Management
The system SHALL initialize database resources in `app.state` during the lifespan and dispose them cleanly on shutdown.

#### Scenario: Database engine initialized in lifespan
- **WHEN** la aplicación FastAPI completa su fase de arranque del lifespan
- **THEN** `app.state.engine` y `app.state.session_factory` están instanciados y disponibles para las peticiones

#### Scenario: Clean engine shutdown
- **WHEN** la aplicación FastAPI recibe una señal de apagado
- **THEN** se invoca `engine.dispose()` liberando las conexiones activas del pool

### Requirement: Operational Health Verification
The system SHALL expose health verification endpoints distinguishing between liveness and readiness.

#### Scenario: Liveness check succeeds without database
- **WHEN** un cliente realiza una petición `GET /health/live`
- **THEN** el sistema responde con código HTTP 200 y mensaje de proceso activo sin consultar la base de datos

#### Scenario: Readiness check with healthy database
- **WHEN** un cliente realiza una petición `GET /health/ready` y la base de datos responde exitosamente a `SELECT 1`
- **THEN** el sistema responde con código HTTP 200 y estado listo

#### Scenario: Readiness check with unreachable database
- **WHEN** un cliente realiza una petición `GET /health/ready` y la base de datos no contesta o rechaza la conexión
- **THEN** el sistema responde con código HTTP 503 Service Unavailable
