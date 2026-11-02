# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **Taller Mecánico API**.
> Cada change es atómico: un agente puede implementarlo en una sesión (~4-6 horas).
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

---

## Cómo usar este documento

1. Identificar el change a implementar (verificar que sus dependencias están archivadas en `openspec/changes/archive/`).
2. Leer los documentos de la Knowledge Base indicados en la sección "Leer antes" del change.
3. Ejecutar `/opsx:propose <nombre-del-change>` para planificar e implementar la funcionalidad.
4. Al terminar la verificación del change, archivarlo con `/opsx:archive <nombre-del-change>`.
5. Marcar el checkbox `[x]` correspondiente en este archivo para actualizar el avance del proyecto.

---

## Árbol de dependencias

```
C-01 foundation-config-lifespan
  └── C-02 domain-models-migrations-seed
        └── C-03 core-uow-repository-contracts
              └── C-04 auth-security-session             ← desbloquea capas de negocio
                    │
                    ├── C-05 authorization-rbac-protection
                    │     │
                    │     ├── C-06 clientes-vehiculos-module
                    │     │     │
                    │     │     └── C-08 ordenes-trabajo-execution-module (requiere C-06 y C-07)
                    │     │           └── C-09 verification-suite-e2e-docs
                    │     │
                    │     └── C-07 repuestos-stock-precios-module (paralelo con C-06)
```

### Paralelismo por fase

> Cada "gate" es un punto de sincronización. Los changes dentro de un mismo grupo pueden ejecutarse en paralelo por agentes distintos.

```
GATE 0: ninguna
  → C-01 foundation-config-lifespan (solo)

GATE 1: C-01 ✓
  → C-02 domain-models-migrations-seed (solo)

GATE 2: C-02 ✓
  → C-03 core-uow-repository-contracts (solo)

GATE 3: C-03 ✓
  → C-04 auth-security-session (solo)

GATE 4: C-04 ✓
  → C-05 authorization-rbac-protection (solo)

GATE 5: C-05 ✓                                           ← FORK DE NEGOCIO (2 paralelos)
  → C-06 clientes-vehiculos-module                       [Agente A]
  → C-07 repuestos-stock-precios-module                  [Agente B]

GATE 6: C-06 + C-07 ✓
  → C-08 ordenes-trabajo-execution-module (solo)

GATE 7: C-08 ✓
  → C-09 verification-suite-e2e-docs (solo)
```

### Camino crítico (7 changes — mínimo irreducible)

```
C-01 → C-02 → C-03 → C-04 → C-05 → C-06 → C-08 → C-09
```

### Plan óptimo con 3 agentes

```
Paso │ Agente A (Core & Entidades)    │ Agente B (Stock & Auxiliar)       │ Agente C (Verificación/QA)
─────┼────────────────────────────────┼───────────────────────────────────┼───────────────────────────
  1  │ C-01 foundation-config-lifespan│                 —                 │             —
  2  │ C-02 domain-models-migrations  │                 —                 │             —
  3  │ C-03 core-uow-repository-base  │                 —                 │             —
  4  │ C-04 auth-security-session     │                 —                 │             —
  5  │ C-05 authorization-rbac        │                 —                 │             —
  6  │ C-06 clientes-vehiculos-module │ C-07 repuestos-stock-precios-mod  │ Preparar harness .http
  7  │ C-08 ordenes-trabajo-execution │                 —                 │ Test casos C-10 a C-13
  8  │                 —              │                 —                 │ C-09 verification-suite
```

---

## FASE 0 — Cimientos y Ciclo de Vida

### [C-01] `foundation-config-lifespan`
- **Estado**: `[x]` completado (archivado)
- **Scope**: Estructura de carpetas obligatoria, configuración con `pydantic-settings` y ciclo de vida ASGI
  - Configuración en `app/core/config.py` con `BaseSettings`, `@computed_field` para armado de URL `postgresql+asyncpg://`, sin secretos por defecto (falla si faltan `POSTGRES_PASSWORD` o `JWT_SECRET_KEY`)
  - `app/core/database.py`: motor asincrónico SQLAlchemy con `pool_size` configurable, `async_sessionmaker(expire_on_commit=False)` y función `get_session`
  - Lifespan en `main.py`: crea motor y sesión en `app.state`, precalcula hash ficticio de bcrypt y ejecuta `engine.dispose()` al cerrar
  - Endpoints de salud en `app/modules/health/router.py`: `GET /health/live` (200 sin BD) y `GET /health/ready` (ejecuta `SELECT 1`, responde 200 o 503)
  - Tests unitarios de arranque y salud
- **Dependencias**: ninguna
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/01_vision_y_objetivos.md` §Alcance
  - `knowledge-base/02_descripcion_general.md` §Stack y Arquitectura
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura y Variables de entorno

---

### [C-02] `domain-models-migrations-seed`
- **Estado**: `[x]` completado (archivado)
- **Scope**: Modelos de datos del dominio, relaciones, índices únicos parciales, plantilla Alembic asincrónica y datos iniciales
  - Modelos SQLModel/SQLAlchemy para las 13 tablas: `usuario`, `asignacion_rol`, `intento_acceso`, `evento_seguridad`, `cliente`, `vehiculo`, `repuesto`, `estado_orden`, `orden_trabajo`, `item_orden`, `historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto`
  - Índices únicos parciales en BD (`postgresql_where`): patente no borrada, código de repuesto no borrado, rol activo no revocado
  - Migración 001 (autogenerada): esquema completo con tablas, tipos NUMERIC, timestamptz, CHECKs y FKs con índices
  - Migración 002 (manual): función PL/pgSQL y disparadores de rechazo BEFORE UPDATE OR DELETE sobre las 3 tablas de sólo agregado (RN-15)
  - `seed.py`: vaciado de tablas y carga inicial de catálogo de estados, usuarios de prueba, Laura y Jorge con vehículos, repuestos iniciales y movimientos
  - Verificación `alembic upgrade head`, `downgrade base` y re-upgrade
- **Dependencias**: C-01
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Entidades y Seed data
  - `knowledge-base/05_reglas_de_negocio.md` (RN-01, RN-15, RN-19)
  - `knowledge-base/08_arquitectura_propuesta.md` §Migración manual de triggers
  - `knowledge-base/09_decisiones_y_supuestos.md` (DD-01, DD-06)

---

## FASE 1 — Infraestructura Core, Contratos y Seguridad

### [C-03] `core-uow-repository-contracts`
- **Estado**: `[x]` completado (archivado)
- **Scope**: Repositorios base genéricos, Unit of Work abstracto y envoltorio de paginación
  - `app/core/repository.py`: `BaseRepository[T]` genérico (`get_by_id`, `get_all`, `count`, `add`, `update`, `delete`) con `session.flush()` y prohibición absoluta de `commit()`; `SoftDeleteRepository[T]` que filtra borrados lógicos y añade `soft_delete()`
  - `app/core/unit_of_work.py`: `UnitOfWork` base como gestor de contexto asincrónico (`async with uow:`), confirma en salida limpia, revierte ante excepción y no cierra la sesión
  - `app/core/paginacion.py`: envoltorio `{items, total, page, size, pages}`, `page` desde 1, `size` 1 a 100 (default 20), responde 422 si la página solicitada excede la última
  - Contratos base Pydantic con `model_config = ConfigDict(extra="forbid")`
  - Tests unitarios de rollback automático de UoW y paginación
- **Dependencias**: C-02
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/02_descripcion_general.md` §Arquitectura en capas
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados
  - `knowledge-base/09_decisiones_y_supuestos.md` (DD-06)

---

### [C-04] `auth-security-session`
- **Estado**: `[x]` completado (archivado)
- **Scope**: Autenticación segura, bcrypt off-loop con semáforo, cookie HttpOnly y rate limit con timing defense
  - `app/core/security.py`: `hash_password` y `verify_password` ejecutados con `asyncio.to_thread` acotados por `asyncio.Semaphore(MAX_CONCURRENT_BCRYPT)`, límite estricto de 72 bytes en entrada
  - `POST /auth/login`: verificación previa de 5 intentos fallidos en 60s por (email, ip) sobre `intento_acceso` (responde 429 con `Retry-After`); si pasa, verifica contra hash real o hash ficticio precalculado (RN-09); registro de intento en sesión y transacción independiente confirmada
  - Emisión de JWT firmado con `sub`, `iat`, `exp` y roles vigentes; empaquetado exclusivamente en cabecera `Set-Cookie: access_token=...; HttpOnly; SameSite=Lax; Max-Age=1800` (el body no incluye token)
  - `POST /auth/logout`: borrado de cookie con `Max-Age=0`
  - `POST /auth/registro`: alta atómica en un único UoW de `usuario`, rol `CLIENTE` y ficha `cliente` (RN-02); responde 201 o 409
  - `GET /auth/yo`: devuelve usuario autenticado, roles vigentes en BD y roles informados en el token
- **Dependencias**: C-03
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md`
  - `knowledge-base/05_reglas_de_negocio.md` (RN-02, RN-08, RN-09)
  - `knowledge-base/07_flujos_principales.md` §Flujo 1 y Flujo 2
  - `knowledge-base/09_decisiones_y_supuestos.md` (DD-02, DD-03, DD-04)

---

### [C-05] `authorization-rbac-protection`
- **Estado**: `[x]` completado (archivado)
  - **Nota**: la tarea 7.3 y la suite de archivos `.http` de los casos de cátedra se transfieren a **C-09** `verification-suite-e2e-docs`, conforme a su scope; su ejecución requiere PostgreSQL real más `python seed.py`.
- **Scope**: Dependencias de autorización RBAC en base de datos, autoprotección de administradores y cambio obligatorio de contraseña
  - `app/core/dependencies.py`: `get_usuario_actual` (lee cookie, valida JWT y verifica usuario activo); `requiere_rol(roles)` consultando en cada request las filas vigentes en `asignacion_rol` (RN-04)
  - Autoprotección admin: el administrador no puede revocarse a sí mismo el rol `ADMIN` ni dejar al sistema sin administradores vigentes (409) (RN-05)
  - Rutas de personal: `POST /usuarios` (alta con clave provisoria y `debe_cambiar_password=True`), `GET /usuarios/{id}/roles`, `POST /usuarios/{id}/roles` (vencimiento en el futuro con zona horaria o 422), `DELETE /usuarios/{id}/roles/{rol}`
  - Dos grupos de rutas en `main.py`: grupo Abierto y grupo Protegido montado con dependencia que bloquea con 403 si `debe_cambiar_password=True`
  - `POST /auth/cambiar-password`: actualiza clave, apaga bandera obligatoria y registra `password_cambiada_en = NOW()`; sesiones previas devuelven 401 comparando `iat` sin truncar a segundos (RN-07)
  - Registro de altas y modificaciones en `evento_seguridad` con actor correspondiente
- **Dependencias**: C-04
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` §Matriz RBAC y Autoprotección
  - `knowledge-base/05_reglas_de_negocio.md` (RN-03, RN-04, RN-05, RN-06, RN-07)
  - `knowledge-base/07_flujos_principales.md`
  - `knowledge-base/09_decisiones_y_supuestos.md` (DD-05)

---

## FASE 2 — Módulos de Clientes y Repuestos (Paralelizables)

### [C-06] `clientes-vehiculos-module`
- **Estado**: `[x]` completado (archivado)
- **Scope**: Gestión de clientes, flota de vehículos y borrado lógico con validación de órdenes abiertas
  - Repositorio y UoW de clientes: `POST /clientes` (documento único), `GET /clientes/{id}` con precarga de vehículos
  - Repositorio de vehículos (SoftDelete): `POST /clientes/{id}/vehiculos` (patente única vigente, año 1950..2100)
  - `DELETE /vehiculos/{id}`: borrado lógico (`borrado_en = NOW()`); si el vehículo tiene órdenes con estado `es_final=False`, rechaza con 409 (RN-16); si no, responde 204
  - `GET /mis-vehiculos`: cliente autenticado consulta únicamente sus vehículos vigentes (RN-17)
  - Registro de vehículos vendidos con misma patente para otro cliente (C-19)
- **Dependencias**: C-05
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §cliente y vehiculo
  - `knowledge-base/05_reglas_de_negocio.md` (RN-01, RN-16, RN-17)
  - `knowledge-base/06_funcionalidades.md` §Épica 3

---

### [C-07] `repuestos-stock-precios-module`
- **Estado**: `[ ]` pendiente
- **Scope**: Catálogo de repuestos, reposición de stock, auditoría atómica de precios e historial de sólo agregado
  - Repositorio de repuestos (SoftDelete): `GET /repuestos` con búsqueda por `q`, paginación segura y parámetros ligados; `GET /repuestos/{id}`
  - `POST /repuestos`: alta con `stock_inicial` generando el movimiento inicial
  - `PATCH /repuestos/{id}`: modificación de descripción y precio (rechaza `stock` con 422 `extra="forbid"` por RN-14); si cambia el precio, inserta fila en `historial_precio_repuesto` en la misma transacción (RN-20); si el precio no varía, no inserta historial
  - `DELETE /repuestos/{id}`: borrado lógico (204)
  - `POST /repuestos/{id}/reponer`: mutación controlada de stock con inserción de `movimiento_stock`
  - `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios`
- **Dependencias**: C-05
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §repuesto y movimientos
  - `knowledge-base/05_reglas_de_negocio.md` (RN-14, RN-15, RN-20)
  - `knowledge-base/06_funcionalidades.md` §Épica 4

---

## FASE 3 — Órdenes de Trabajo y Transaccionalidad Compleja

### [C-08] `ordenes-trabajo-execution-module`
- **Estado**: `[ ]` pendiente
- **Scope**: Ciclo de vida completo de órdenes de trabajo, transacciones atómicas de stock, background tasks y catálogo de estados
  - Catálogo: `GET /estados-orden` ordenado por posición vía repositorio de sólo lectura; si la tabla está vacía, crear órdenes da 409 (RN-19)
  - `POST /ordenes`: crea orden `PENDIENTE`, valida al menos un ítem y sin repuestos repetidos (RN-10); copia precios vigentes, calcula total en servidor y registra primera fila en `historial_estado_orden`
  - `GET /ordenes` (filtrable por estado y paginada) y `GET /ordenes/{id}` con carga anticipada fija sin N+1 (vehículo, cliente, ítems, repuestos e historial)
  - `POST /ordenes/{id}/iniciar`: mecánico se auto-asigna y pasa orden a `EN_REPARACION` (RN-11)
  - `POST /ordenes/{id}/terminar`: mecánico asignado o admin finaliza orden en un único UoW atómico: descuenta stock de cada ítem, inserta `movimiento_stock` por cada ítem, actualiza a `TERMINADA` e inserta `historial_estado_orden`; si algún stock no alcanza, rollback total y 409 (RN-13); al confirmar, despacha `BackgroundTasks` con `asyncio.sleep(0.5)` y log de aviso simulado (Ej. 8)
  - `POST /ordenes/{id}/cancelar`: evalúa permisos antes que estado (dueño, recepción o admin da 403 antes que 409) (RN-12)
  - `GET /mis-ordenes`: cliente consulta únicamente órdenes asociadas a sus vehículos (RN-17)
- **Dependencias**: C-06, C-07
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §orden_trabajo, item_orden e historial
  - `knowledge-base/05_reglas_de_negocio.md` (RN-10, RN-11, RN-12, RN-13, RN-17, RN-19)
  - `knowledge-base/07_flujos_principales.md` §Flujo 3 y Flujo 4
  - `knowledge-base/08_arquitectura_propuesta.md`

---

## FASE 4 — Verificación E2E y Entregables Finales

### [C-09] `verification-suite-e2e-docs`
- **Estado**: `[ ]` pendiente
- **Scope**: Suite completa de pruebas de cátedra (.http y SQL), verificación de consultas sin N+1, env.example y README de puesta en marcha
  - Directorio `test/` con archivos `.http`: `test/auth.http` (C-01 a C-09 con manejo de multi-sesión `# @no-cookie-jar`), `test/ordenes.http` (C-10 a C-13) y `test/repuestos_vehiculos.http` (C-16 a C-19)
  - `test/solo_agregado.sql`: script de prueba de los 6 rechazos del disparador de sólo agregado y la clave foránea del catálogo (C-14)
  - Verificación del recuento de consultas SQL sin N+1 (`SQL_ECHO=true`) comparando orden con 2 y 4 ítems (C-15)
  - `env.example` completo sin secretos y `alembic.ini`
  - `README.md` de entrega: instrucciones paso a paso (venv, dependencias, env, migración, seed y arranque del servidor)
- **Dependencias**: C-08
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/01_vision_y_objetivos.md` §Métricas de éxito
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios
  - `knowledge-base/09_decisiones_y_supuestos.md` §Entorno de evaluación
