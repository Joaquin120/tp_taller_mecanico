# Visión y Objetivos

## Propósito del sistema
Construir una API RESTful asincrónica en capas para la gestión integral de un taller mecánico (clientes, vehículos, órdenes de trabajo, control de repuestos/stock y control de acceso RBAC). El sistema garantiza la integridad transaccional mediante Unit of Work, asegura la persistencia con PostgreSQL y migraciones Alembic, e implementa autenticación y autorización robusta sin exponer datos sensibles.

## Objetivos por actor

| Actor | Objetivo Principal | Objetivos Secundarios |
| :--- | :--- | :--- |
| **Administrador** | Gestión global del taller, personal y catálogo | Asignar/revocar roles vigentes, reponer stock de repuestos, actualizar precios, auditar eventos de seguridad y terminar/cancelar órdenes |
| **Recepción** | Atención inicial al cliente y recepción de vehículos | Alta de clientes y vehículos, apertura de órdenes de trabajo con sus fallas e ítems, cancelación de órdenes a pedido |
| **Mecánico** | Ejecución técnica y reparación | Consultar órdenes pendientes, tomar e iniciar órdenes (auto-asignación), terminar reparaciones con descuento automático de repuestos |
| **Cliente** | Seguimiento de sus vehículos y servicios | Auto-registro en la web, consulta de sus vehículos propios (`/mis-vehiculos`), órdenes asociadas (`/mis-ordenes`) y cancelación de sus órdenes pendientes |
| **SISTEMA** | Registro de auditoría y trazabilidad | Anotación de inicialización de datos (seed) y auditoría sin depender de un usuario físico |

## Alcance v1.0 (Capítulos 1 a 6)
- **Fundamentos FastAPI (Cap. 1):** Aplicación asincrónica, lifespan explícito, creación de motor y sessionmaker en `app.state`, endpoints `/health/live` y `/health/ready`.
- **Contratos y CRUD (Cap. 2):** DTOs Pydantic con `extra="forbid"`, respuestas tipadas sin exponer `password_hash`, envoltorio estándar de paginación (`items`, `total`, `page`, `size`, `pages`).
- **Ejecución Asincrónica (Cap. 3):** Todos los handlers declarados con `async def`, llamadas costosas (bcrypt) delegadas fuera del bucle (`asyncio.to_thread`) bajo semáforo concurrente, tareas en segundo plano simuladas (`BackgroundTasks`).
- **Persistencia y Migraciones (Cap. 4):** Modelos SQLModel/SQLAlchemy, relaciones 1:1, 1:N y N:M, catálogo de estados con FK, tres índices únicos parciales (`postgresql_where`), dos migraciones Alembic (una autogenerada y una manual con disparadores PL/pgSQL).
- **Autenticación y Autorización (Cap. 5):** Passwords con bcrypt, token JWT en cookie `HttpOnly` (`SameSite=Lax`, `Max-Age`), control de rate limit de login con hash ficticio, RBAC dinámico evaluado en base de datos en cada petición, invalidación inmediata por cambio de contraseña comparando `iat` con `password_cambiada_en` sin truncar.
- **Repositorios, Unit of Work y Transacciones (Cap. 6):** Jerarquía `BaseRepository[T]` y `SoftDeleteRepository[T]`, `flush()` sin `commit()` en repositorios, Unit of Work por módulo como context manager asincrónico, tablas de sólo agregado protegidas por disparadores, transacción aislada para `intento_acceso`.

## Fuera de alcance
- **Control de concurrencia pesimista/optimista (Cap. 7):** No se implementan bloqueos `SELECT FOR UPDATE` ni aislamiento serializable; se acepta la actualización perdida por concurrencia simultánea en terminación de órdenes.
- **Colas distribuidas y workers con Redis / Celery (Cap. 8):** El aviso por mail/mensaje al cliente se resuelve mediante `BackgroundTasks` en memoria en el mismo proceso FastAPI.
- **Edición manual de stock:** El stock de repuestos no admite modificación por `PATCH`; solo muta mediante movimientos registrados (alta inicial, reposición o terminación de orden).

## Métricas de éxito y criterios de evaluación
- 100% de los 8 ejercicios del trabajo práctico implementados y aprobados.
- Paso exitoso de los 19 casos de prueba mínimos (C-01 a C-19) detallados en `test/` mediante `.http` y `solo_agregado.sql`.
- Esquema versionado reproducible mediante `alembic upgrade head` sobre base limpia, `alembic downgrade base` y re-upgrade sin fallos.
- Cero fugas de contraseñas, secretos o mensajes de error internos de PostgreSQL hacia el cliente.
