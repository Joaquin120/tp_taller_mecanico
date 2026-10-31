# Skill Registry — Taller Mecánico API

> Catálogo canónico de skills disponibles para el proyecto con reglas compactas pre-digeridas.
> Generado automáticamente por `skill-registry`. No editar a mano.

---

## Índice de Skills Disponibles

| Skill | Tipo | Disparadores / Cuándo Usar | Resumen |
| :--- | :--- | :--- | :--- |
| **`fastapi`** | Dominio / Framework | Rutas, handlers, lifespan, Depends, middleware | Buenas prácticas de FastAPI asincrónico, contratos DTO y ciclo de vida en `app.state`. |
| **`clean-architecture`** | Arquitectura | Capas, desacoplamiento, límites de interfaces | Separación estricta: `Router -> Service -> UoW -> Repository -> Model`. |
| **`domain-driven-design`** | Arquitectura | Entidades, Value Objects, invariantes, RN | Modelado del dominio, reglas de negocio atómicas y agregados. |
| **`sqlalchemy-alembic-expert`**| Persistencia | SQLAlchemy 2.0 async, migraciones, sesiones | Gestión asincrónica de sesiones, `selectinload` sin N+1 y migraciones Alembic. |
| **`python-testing-patterns`** | Testing / QA | Tests unitarios, integración, pytest-asyncio | Patrones de prueba para endpoints HTTP, manejo de cookies y transacciones de test. |

---

## Reglas Compactas por Skill

### `fastapi`
- Todos los route handlers DEBEN declararse con `async def`. Ninguna llamada bloqueante en el event loop.
- Dependencias inyectadas con `Depends()` (ej. `get_session`, `get_usuario_actual`, `requiere_rol`).
- Contratos de entrada y salida desacoplados con Pydantic (`extra="forbid"`); jamás devolver `password_hash`.
- El ciclo de vida (`lifespan`) crea el motor y la fábrica de sesiones y los aloja en `app.state`.

### `clean-architecture`
- Los routers sólo desempaquetan la petición HTTP, construyen el UoW y llaman al servicio. No contienen SQL ni lógica de negocio.
- Los servicios encapsulan las reglas de negocio (RN-01 a RN-20). Abren el UoW (`async with uow:`) pero nunca lo construyen.
- Los repositorios abstraen consultas de BD y ejecutan `session.flush()`. NUNCA ejecutan `commit()`.
- El Unit of Work coordina la transacción atómica compartida y confirma al salir del bloque.

### `domain-driven-design`
- Las entidades del dominio preservan invariantes de negocio (ej. totales calculados, comprobaciones de stock).
- Diferenciar entidades con identidad (`orden_trabajo`, `vehiculo`) de catálogos y referencias inmutables (`estado_orden`).
- Garantizar que las mutaciones complejas (terminar orden + restar stock + movimiento + historial) se comporten como un agregado atómico.

### `sqlalchemy-alembic-expert`
- Usar SQLAlchemy 2.0 con sintaxis `select(...)` y motor asincrónico (`postgresql+asyncpg`).
- Sesiones instanciadas con `expire_on_commit=False`.
- Prohibida la carga perezosa (lazy load): precargar relaciones con `selectinload()` o `joinedload()` en el método del repositorio.
- Triggers PL/pgSQL y funciones de base de datos se versionan mediante migraciones manuales de Alembic.

### `python-testing-patterns`
- Pruebas HTTP con clientes asincrónicos (`httpx.AsyncClient`) o suites `.http` estructuradas.
- Validar siempre los códigos de estado esperados (200, 201, 204, 401, 403, 404, 409, 422, 503).
- Probar multi-sesión aislando cookies de autenticación (`# @no-cookie-jar`).
- Ejecutar `seed.py` antes de las corridas de prueba para asegurar un estado conocido.
