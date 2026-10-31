# Descripción General

## Stack tecnológico

| Componente | Versión mínima | Uso en el proyecto |
| :--- | :--- | :--- |
| **Python** | 3.12+ | Lenguaje base |
| **FastAPI** | 0.111+ | Framework web asincrónico (todos los handlers con `async def`) |
| **SQLModel** | 0.0.24+ | Modelos de tabla y esquemas base compatibles con SQLAlchemy y Pydantic |
| **SQLAlchemy** | 2.0+ (async) | Motor asincrónico, fábrica de sesiones (`async_sessionmaker`), consultas con carga anticipada (`selectinload` / `joinedload`) |
| **asyncpg** | 0.30+ | Controlador/driver asincrónico para PostgreSQL (`postgresql+asyncpg://...`) |
| **PostgreSQL** | 16+ | Motor de base de datos relacional |
| **Alembic** | 1.13+ | Herramienta de migraciones con plantilla asincrónica |
| **pydantic-settings** | 2.0+ | Configuración tipada leída desde entorno o `.env` mediante `@computed_field` |
| **bcrypt** | 4.0+ | Algoritmo de hash de contraseñas (ejecución fuera del loop de eventos) |
| **PyJWT** | 2.8+ | Generación y verificación de tokens JWT firmados |
| **uvicorn** | [standard] | Servidor de aplicaciones ASGI |

## Arquitectura general en capas

El sistema sigue una arquitectura estricta en 6 capas desacopladas por módulo funcional:

```
[Cliente HTTP / Frontend]
        │  (Petición HTTP + Cookie access_token)
        ▼
   [ Router ]            <-- app/modules/<módulo>/router.py
        │                    Construye el UoW, invoca al Service, traduce errores (HTTP status)
        ▼
   [ Service ]           <-- app/modules/<módulo>/service.py
        │                    Reglas de negocio (RN-01 a RN-20). Abre `async with uow:`
        ▼
[ Unit of Work (UoW) ]   <-- app/modules/<módulo>/unit_of_work.py
        │                    Coordina transacciones atómicas. Confirma (commit) o revierte (rollback)
        ▼
  [ Repository ]         <-- app/modules/<módulo>/repository.py
        │                    Abstracción de persistencia. Métodos add(), update(), flush(). Cero commit.
        ▼
    [ Model ]            <-- app/modules/<módulo>/models.py
        │                    Entidades SQLModel/SQLAlchemy y restricciones de base de datos
        ▼
 [ PostgreSQL 16 ]
```

### Separación de grupos de rutas (Mounting)
FastAPI suma dependencias y no permite restarlas. Por lo tanto, `main.py` define dos routers principales:
1. **Grupo Abierto:** Rutas de salud (`/health/*`) y autenticación pública (`/auth/registro`, `/auth/login`, `/auth/logout`, `/auth/yo`, `/auth/cambiar-password`).
2. **Grupo Protegido:** Contiene el resto de las operaciones de negocio (`/usuarios`, `/clientes`, `/vehiculos`, `/repuestos`, `/ordenes`, `/eventos`, `/estados-orden`, `/mis-*`). Lleva montada una dependencia global que exige token válido Y bloquea a usuarios con `debe_cambiar_password=True` con un HTTP 403.

## Resumen de endpoints principales

| Recurso | Métodos y Rutas | Descripción | Acceso |
| :--- | :--- | :--- | :--- |
| **Salud** | `GET /health/live`<br>`GET /health/ready` | Liveness (proceso activo) y Readiness (`SELECT 1` a PostgreSQL) | Público |
| **Autenticación** | `POST /auth/registro`<br>`POST /auth/login`<br>`POST /auth/logout`<br>`GET /auth/yo`<br>`POST /auth/cambiar-password` | Gestión de sesiones con cookie `HttpOnly`, rate-limit y cambio forzado | Público / Autenticado |
| **Usuarios** | `POST /usuarios`<br>`GET /usuarios/{id}/roles`<br>`POST /usuarios/{id}/roles`<br>`DELETE /usuarios/{id}/roles/{rol}` | Creación de personal y gestión de asignaciones de roles con vigencia | ADMIN |
| **Eventos** | `GET /eventos` | Auditoría de seguridad paginada | ADMIN |
| **Clientes** | `POST /clientes`<br>`GET /clientes/{id}` | Gestión de fichas de clientes y consulta con vehículos asociados | RECEPCION, ADMIN |
| **Vehículos** | `POST /clientes/{id}/vehiculos`<br>`DELETE /vehiculos/{id}`<br>`GET /mis-vehiculos` | Alta y borrado lógico de vehículos; consulta propia por cliente | RECEPCION, ADMIN / Dueño |
| **Repuestos** | `GET /repuestos`<br>`GET /repuestos/{id}`<br>`POST /repuestos`<br>`PATCH /repuestos/{id}`<br>`DELETE /repuestos/{id}`<br>`POST /repuestos/{id}/reponer`<br>`GET /repuestos/{id}/movimientos`<br>`GET /repuestos/{id}/precios` | Catálogo, búsqueda filtrada, reposición de stock, historial inmutable de precios y movimientos | ADMIN, RECEPCION, MECANICO |
| **Órdenes** | `POST /ordenes`<br>`GET /ordenes`<br>`GET /ordenes/{id}`<br>`POST /ordenes/{id}/iniciar`<br>`POST /ordenes/{id}/terminar`<br>`POST /ordenes/{id}/cancelar`<br>`GET /mis-ordenes` | Ciclo de vida completo de la orden de trabajo | RECEPCION, ADMIN, MECANICO, Dueño |
| **Catálogo** | `GET /estados-orden` | Lectura de estados ordenados por posición | Autenticado |
