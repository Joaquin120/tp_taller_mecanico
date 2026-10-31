# Arquitectura Propuesta

## Patrones Arquitectónicos Aplicados

| Patrón | Dónde se aplica | Propósito y Justificación |
| :--- | :--- | :--- |
| **Separación en Capas** | Todo el sistema (`Router -> Service -> UoW -> Repository -> Model`) | Cada capa conoce únicamente a su inmediata inferior. Handlers del Router no contienen lógica de SQL ni de negocio. |
| **Repository Pattern** | `app/core/repository.py` y repositorios por módulo | `BaseRepository[T]` y `SoftDeleteRepository[T]`. Aislar el acceso a datos. Los repositorios ejecutan `flush()`, NUNCA `commit()`. |
| **Unit of Work (UoW)** | `app/core/unit_of_work.py` y `app/modules/<módulo>/unit_of_work.py` | Context manager asincrónico (`async with uow:`). Gestiona la transacción compartida por todos los repositorios del módulo y asegura `commit()` o `rollback()`. No cierra la sesión de BD. |
| **Dependency Injection** | Handlers de FastAPI (`Depends(...)`) | Inyección de fábrica de sesiones (`get_session`), UoW en el router, dependencias de autenticación y autorización (`get_usuario_actual`, `requiere_rol`). |
| **Off-loop CPU Bound Task** | `app/core/security.py` | Ejecución de funciones costosas de bcrypt en `asyncio.to_thread` bajo un `asyncio.Semaphore` para no bloquear el bucle de eventos. |
| **Sólo Agregado (Append-Only)** | Tablas de auditoría y movimientos | Impedir `UPDATE` y `DELETE` en la base de datos mediante triggers PostgreSQL instalados en la migración manual. |

## Estructura de Directorios Obligatoria

```text
tp_taller_mecanico/
├── main.py                               # App FastAPI, lifespan, montaje de grupos abierto y protegido
├── seed.py                               # Siembra de base de datos con datos mínimos de prueba
├── requirements.txt                      # Dependencias Python fijadas
├── env.example                           # Variables de entorno de ejemplo sin secretos
├── alembic.ini                           # Configuración de migraciones Alembic
├── migrations/                           # Entorno y versiones de Alembic
│   ├── env.py                            # Configuración asincrónica de Alembic
│   ├── script.py.mako
│   └── versions/
│       ├── 001_initial_schema.py         # 1ra migración: tablas, restricciones e índices únicos parciales
│       └── 002_triggers_solo_agregado.py # 2da migración (a mano): disparadores PL/pgSQL
├── app/
│   ├── core/
│   │   ├── config.py                     # Settings pydantic-settings con @computed_field
│   │   ├── database.py                   # engine, sessionmaker en app.state, get_session
│   │   ├── security.py                   # bcrypt fuera del loop, semáforo, JWT emisión/verificación
│   │   ├── dependencies.py               # usuario actual, roles vigentes en BD, control cambio contraseña, requiere_rol
│   │   ├── repository.py                 # BaseRepository[T] y SoftDeleteRepository[T]
│   │   ├── paginacion.py                 # Envoltorio {items, total, page, size, pages}
│   │   └── unit_of_work.py               # UnitOfWork base abstracto (async context manager)
│   └── modules/
│       ├── health/
│       │   └── router.py                 # /health/live y /health/ready
│       ├── usuarios/
│       │   ├── models.py                 # Usuario, AsignacionRol, IntentoAcceso, EventoSeguridad
│       │   ├── schemas.py                # Contratos DTO con extra="forbid"
│       │   ├── repository.py             # Repositorios de usuarios, roles, intentos y eventos
│       │   ├── unit_of_work.py           # UsuariosUnitOfWork
│       │   ├── service.py                # Lógica de login, intentos, personal y roles
│       │   └── router.py                 # Rutas /auth y /usuarios
│       ├── clientes/
│       │   ├── models.py                 # Cliente, Vehiculo
│       │   ├── schemas.py
│       │   ├── repository.py             # ClienteRepository, VehiculoRepository (SoftDelete)
│       │   ├── unit_of_work.py
│       │   ├── service.py
│       │   └── router.py                 # /clientes, /vehiculos, /mis-vehiculos
│       ├── repuestos/
│       │   ├── models.py                 # Repuesto, MovimientoStock, HistorialPrecioRepuesto
│       │   ├── schemas.py
│       │   ├── repository.py             # RepuestoRepository (SoftDelete), Movimiento, HistorialPrecio
│       │   ├── unit_of_work.py
│       │   ├── service.py
│       │   └── router.py                 # /repuestos, /movimientos, /precios
│       └── ordenes/
│           ├── models.py                 # EstadoOrden (catálogo), OrdenTrabajo, ItemOrden, HistorialEstadoOrden
│           ├── schemas.py
│           ├── repository.py             # EstadoOrdenRepository (solo lectura), OrdenTrabajoRepository
│           ├── unit_of_work.py
│           ├── service.py
│           └── router.py                 # /ordenes, /estados-orden, /mis-ordenes
├── test/
│   ├── solo_agregado.sql                 # Prueba directa en psql de disparadores de rechazo
│   ├── auth.http                         # Casos C-01 a C-09
│   ├── ordenes.http                      # Casos C-10 a C-15
│   └── repuestos_vehiculos.http          # Casos C-16 a C-19
└── knowledge-base/                       # Base de conocimiento canónica
```

## Configuración y Variables de Entorno

La configuración se implementa con `pydantic_settings.BaseSettings`:
- La URL de base de datos se calcula dinámicamente con `@computed_field` a partir de `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` y `POSTGRES_DB` (`postgresql+asyncpg://...`).
- Ni `POSTGRES_PASSWORD` ni `JWT_SECRET_KEY` poseen valores por defecto en el código: si no están definidas, la aplicación falla al arrancar.

| Variable | Tipo | Descripción | Sensible |
| :--- | :--- | :--- | :---: |
| `POSTGRES_USER` | string | Usuario de PostgreSQL | No |
| `POSTGRES_PASSWORD` | string | Contraseña de PostgreSQL | **Sí** |
| `POSTGRES_HOST` | string | Host / IP del servidor de base de datos | No |
| `POSTGRES_PORT` | int | Puerto de PostgreSQL (ej. 5432) | No |
| `POSTGRES_DB` | string | Nombre de la base de datos | No |
| `DATABASE_POOL_SIZE` | int | Tamaño del connection pool de SQLAlchemy (ej. 10) | No |
| `JWT_SECRET_KEY` | string | Clave secreta simétrica para firma de tokens HS256 | **Sí** |
| `JWT_ALGORITHM` | string | Algoritmo de firma (default `HS256`) | No |
| `JWT_EXPIRATION_SECONDS`| int | Duración del token en segundos (default `1800` = 30 min) | No |
| `COOKIE_SECURE` | bool | Atributo Secure para cookie en HTTPS (default `False` para dev) | No |
| `BCRYPT_ROUNDS` | int | Costo computacional de bcrypt (default `12`) | No |
| `MAX_CONCURRENT_BCRYPT` | int | Límite del semáforo para operaciones bcrypt (ej. `4`) | No |
| `SQL_ECHO` | bool | Mostrar consultas en consola para diagnóstico | No |

## Migración Manual: Triggers de Sólo Agregado
La segunda migración de Alembic añade una función y triggers en PL/pgSQL:
```sql
CREATE OR REPLACE FUNCTION prohibir_update_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Operación no permitida: la tabla % es de sólo agregado (append-only)', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_solo_agregado_historial_estado
BEFORE UPDATE OR DELETE ON historial_estado_orden
FOR EACH ROW EXECUTE FUNCTION prohibir_update_delete();

CREATE TRIGGER trg_solo_agregado_movimiento_stock
BEFORE UPDATE OR DELETE ON movimiento_stock
FOR EACH ROW EXECUTE FUNCTION prohibir_update_delete();

CREATE TRIGGER trg_solo_agregado_historial_precio
BEFORE UPDATE OR DELETE ON historial_precio_repuesto
FOR EACH ROW EXECUTE FUNCTION prohibir_update_delete();
```
